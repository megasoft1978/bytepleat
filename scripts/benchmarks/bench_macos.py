#!/usr/bin/env python3
"""Verified macOS archive benchmark. Final mode requires recorded worker quiescence."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, random, shutil, signal, statistics, subprocess, sys, tempfile, threading, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO
MANIFEST = Path(__file__).with_name('corpus-manifest.json')
SEED = 20261014

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()

def tree(root):
    root = Path(root); out = []
    for p in sorted(root.rglob('*'), key=lambda x: x.relative_to(root).as_posix().encode()):
        if p.is_symlink(): raise ValueError(f'symlink not supported: {p}')
        if p.is_file(): out.append({'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)})
    return out

def dirs(root):
    root = Path(root)
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir())

def independent_decode_status(record, content_matches, stderr_text=None):
    if record.get('exit_code') == 0 and content_matches:
        return 'pass'
    diagnostics = [line.strip() for line in (stderr_text if stderr_text is not None else record.get('stderr_tail', '')).splitlines() if line.strip()]
    if (record.get('exit_code') == 2 and not record.get('timed_out') and diagnostics
            and all(line.startswith('ERROR: Unsupported Method :') for line in diagnostics)):
        return 'unsupported-method'
    return 'fail'

def unsupported_method_diagnostics(stderr_text):
    diagnostics = [line.strip() for line in stderr_text.splitlines() if line.strip()]
    unsupported = [line for line in diagnostics if line.startswith('ERROR: Unsupported Method :')]
    return {'diagnostic_lines': len(diagnostics), 'unsupported_method_lines': len(unsupported),
            'other_diagnostic_lines': len(diagnostics) - len(unsupported)}

def _kill_group(proc):
    try: os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError: pass

def _wait_one(proc, deadline, timed_out):
    def expire():
        timed_out.set()
        _kill_group(proc)
    timer=threading.Timer(max(0,deadline-time.monotonic()),expire)
    timer.daemon=True; timer.start()
    try:
        _,status,usage=os.wait4(proc.pid,0)
        return (124 if timed_out.is_set() else os.waitstatus_to_exitcode(status)),usage.ru_maxrss
    finally:
        timer.cancel()

def run(argv, cwd, timeout, stderr, stdout=None):
    argv = list(map(str, argv)); start = time.perf_counter(); expired = threading.Event()
    outctx = open(stdout, 'wb') if stdout else open(os.devnull, 'wb')
    try:
        with open(stderr, 'wb') as err, outctx:
            p = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=outctx, stderr=err, start_new_session=True)
            try:
                code, rss = _wait_one(p, time.monotonic() + timeout, expired); p.returncode = code
            finally:
                if p.returncode is None:
                    _kill_group(p); p.wait()
        return {'argv': argv, 'cwd': str(cwd), 'exit_code': code, 'elapsed_seconds': time.perf_counter()-start, 'peak_rss_bytes': rss, 'stderr_tail': Path(stderr).read_text(errors='replace')[-3000:], 'timed_out': expired.is_set()}
    except OSError as e:
        return {'argv': argv, 'cwd': str(cwd), 'exit_code': 127, 'elapsed_seconds': time.perf_counter()-start, 'peak_rss_bytes': None, 'stderr_tail': str(e), 'timed_out': False}

def pipeline(argv1, argv2, cwd, timeout, stderr1, stderr2, output, names=('producer','compressor')):
    """Supervise both pipeline children with blocking wait4 and a timeout thread."""
    start=time.perf_counter(); expired=threading.Event(); procs=[]; timer=None
    try:
        with open(stderr1,'wb') as e1, open(stderr2,'wb') as e2, open(output or os.devnull,'wb') as out:
            p1=subprocess.Popen(list(map(str,argv1)),cwd=cwd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=e1,start_new_session=True)
            procs.append(p1)
            try:
                p2=subprocess.Popen(list(map(str,argv2)),cwd=cwd,stdin=p1.stdout,stdout=out,stderr=e2,start_new_session=True)
                procs.append(p2)
            finally:
                p1.stdout.close()
            def expire():
                expired.set()
                for proc in procs: _kill_group(proc)
            timer=threading.Timer(timeout,expire); timer.daemon=True; timer.start()
            children={}
            for name,proc in zip(names,procs):
                _,status,usage=os.wait4(proc.pid,0)
                proc.returncode=124 if expired.is_set() else os.waitstatus_to_exitcode(status)
                children[name]={'exit_code':proc.returncode,'peak_rss_bytes':usage.ru_maxrss}
            timer.cancel()
        return {'argv':[list(map(str,argv1)),list(map(str,argv2))],'cwd':str(cwd),'exit_code':0 if all(x['exit_code']==0 for x in children.values()) else 1,'child_records':children,'elapsed_seconds':time.perf_counter()-start,'summed_peak_rss_bytes_upper_bound':sum(x['peak_rss_bytes'] for x in children.values()),'rss_note':'sum of per-process peak RSS; upper bound, not simultaneous pipeline peak','stderr_tail':Path(stderr1).read_text(errors='replace')[-1200:]+'\n'+Path(stderr2).read_text(errors='replace')[-1800:],'timed_out':expired.is_set()}
    finally:
        if timer: timer.cancel()
        for proc in procs:
            if proc.returncode is None:
                _kill_group(proc)
                proc.wait()

def verify_prepared(prepared):
    mf=MANIFEST; pf=Path(prepared).resolve()/'PREPARED-MANIFEST.json'
    if not pf.is_file(): raise ValueError('missing prepared public corpus: '+str(pf))
    p=json.loads(pf.read_text()); base=pf.parent
    if not isinstance(p,dict) or p.get('schema')!='bytepleat-public-benchmark-prepared-v1' or p.get('corpus_manifest_sha256')!=sha(mf): raise ValueError('prepared corpus manifest mismatch')
    pin=json.loads(mf.read_text())['derived_ustar']; archive=base/'lz4-v1.10.0.tar'
    if not archive.is_file() or archive.stat().st_size!=pin['bytes'] or sha(archive)!=pin['sha256']: raise ValueError('derived LZ4 USTAR pin mismatch')
    listed=p['files']
    from prepare_public import validate_file_manifest
    validate_file_manifest(listed)
    if any(x.is_symlink() for x in base.rglob('*')): raise ValueError('prepared corpus contains symlinks')
    lz=base/'source-tree/lz4-v1.10.0'
    actual={x['path'] for x in tree(base/'source-tree')}
    if actual!={x['path'] for x in listed}: raise ValueError('prepared LZ4 tree file set differs from manifest')
    for x in listed:
        rel=x['path']; q=base/'source-tree'/rel
        if q.stat().st_size!=x['bytes'] or sha(q)!=x['sha256']: raise ValueError('prepared corpus checksum mismatch: '+rel)
    if not lz.is_dir(): raise ValueError('prepared LZ4 source tree missing')
    return mf,pf,lz,None

def method_table():
    ms=[]
    for f,l in [('zip',6),('zip',9),('7z',5)]: ms.append({'id':f'bytepleat-{f}-{l}','family':'bytepleat','fmt':f,'level':l})
    for f,l in [('zip',6),('zip',9),('7z',5)]: ms.append({'id':f'7zz-{f}-{l}','family':'7zz','fmt':f,'level':l})
    for codec,level in [('zstd',3),('gzip',6),('lz4',0)]:
        ms.append({'id':f'bytepleat-tar-{codec}-{level}' if level else 'bytepleat-tar-lz4','family':'bytepleat','fmt':codec,'level':level})
    for codec,level in [('zstd',3),('gzip',6),('lz4',0)]: ms.append({'id':f'tar-{codec}-{level}' if level else 'tar-lz4','family':'pipe','codec':codec,'level':level})
    ms.append({'id':'native-tar-zstd-3','family':'native-tar','codec':'zstd','level':3})
    ms += [{'id':'ditto-zip','family':'ditto'},{'id':'infozip-6','family':'infozip','level':6}]
    return ms

def tool_versions(paths):
    out={}
    for name,path in paths.items():
        if not path: continue
        path=Path(path).resolve(); version_argv=[str(path)] if name=='rar' else ([str(path),'--version'] if name=='bytepleat' else [str(path),'i'])
        r=subprocess.run(version_argv,capture_output=True,text=True)
        out[name]={'path':str(path),'sha256':sha(path),'version_argv':version_argv,'exit_code':r.returncode,'stdout':r.stdout[:2000],'stderr':r.stderr[:1000]}
    fixed={'ditto':'/usr/bin/ditto','zip':'/usr/bin/zip','unzip':'/usr/bin/unzip','tar':'/usr/bin/tar','sysctl':'/usr/sbin/sysctl'}
    for name in ('ditto','zip','unzip','tar','zstd','lz4','gzip','sysctl'):
        path=fixed.get(name) if fixed.get(name) and Path(fixed[name]).is_file() else (shutil.which(name) or None)
        if path:
            q=Path(path).resolve(); r=subprocess.run([str(q),'--version'],capture_output=True,text=True)
            out[name]={'path':str(q),'sha256':sha(q),'version_exit_code':r.returncode,'version_stdout':(r.stdout+r.stderr)[:1200]}
    return out

def host_snapshot():
    h={'machine':platform.machine(),'platform':platform.platform(),'mac_ver':platform.mac_ver(),'processor':platform.processor(),'load_average':os.getloadavg()}
    for key,value in [('cpu_brand','machdep.cpu.brand_string'),('physical_memory_bytes','hw.memsize'),('cpu_count','hw.ncpu')]:
        q=subprocess.run(['/usr/sbin/sysctl','-n',value],capture_output=True,text=True); h[key]=q.stdout.strip() if q.returncode==0 else None
    return h

def atomic_checkpoint(path,payload):
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(payload,indent=2)+'\n'); os.replace(tmp,path)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--bytepleat',required=True); ap.add_argument('--7zz',dest='seven',required=True); ap.add_argument('--rar'); ap.add_argument('--rar-license-note'); ap.add_argument('--output',required=True); ap.add_argument('--prepared'); ap.add_argument('--repeats',type=int,default=5); ap.add_argument('--timeout',type=int,default=900); ap.add_argument('--allow-smoke',action='store_true'); a=ap.parse_args()
    if sys.platform!='darwin': ap.error('this harness measures macOS only')
    if a.repeats<1 or (a.repeats!=5 and not a.allow_smoke): ap.error('final protocol requires five measured repetitions; smoke may use another positive count')
    if not a.allow_smoke and not a.prepared: ap.error('--prepared is required for final mode')
    if a.rar and not a.rar_license_note: ap.error('--rar-license-note is required when --rar is supplied')
    gate={'status':'not_checked','note':'standalone reproduction; external worker quiescence is not monitored'}
    out=Path(a.output).resolve()
    if out.exists(): ap.error('refusing to overwrite '+str(out))
    if out==ROOT or ROOT in out.parents: ap.error('output must be outside the project repository')
    bp=Path(a.bytepleat).resolve(); zz=Path(a.seven).resolve()
    if not bp.is_file() or not zz.is_file(): ap.error('binary path missing')
    rar=Path(a.rar).resolve() if a.rar else None
    if rar and not rar.is_file(): rar=None
    if a.allow_smoke:
        mf,pf,lz,mix=MANIFEST,None,None,None
    else:
        mf,pf,lz,mix=verify_prepared(a.prepared)
    tools=tool_versions({'bytepleat':bp,'7zz':zz,'rar':rar})
    methods=method_table()
    tar_help=subprocess.run(['/usr/bin/tar','--help'],capture_output=True,text=True)
    native_tar_supported='--zstd' in (tar_help.stdout+tar_help.stderr)
    unavailable=[]
    for m in methods[:]:
        required=('ditto',) if m['family']=='ditto' else ('zip','unzip') if m['family']=='infozip' else ('tar',m['codec']) if m['family']=='pipe' else ()
        missing=[x for x in required if x and not (shutil.which(x) or Path('/usr/bin/'+x).exists())]
        if m['family']=='native-tar' and not native_tar_supported: missing.append('tar native zstd support')
        if missing: methods.remove(m); unavailable.append({'method':m,'reason':'missing executable(s): '+', '.join(missing)})
    skipped=unavailable
    if rar:
        for level in (3,5): methods.append({'id':f'rar5-m{level}','family':'rar','level':level})
    else: skipped.append({'method':'rar5-m3/m5','reason':'local evaluation rar executable unavailable'})
    rng=random.Random(SEED); orders=[]; records=[]; warmups=[]; failures=[]; started=time.time(); state='running'; out.parent.mkdir(parents=True,exist_ok=True)
    rar_eval={'classification':'caller-supplied local executable; not bundled or redistributed','license_note':a.rar_license_note,'executable_sha256':tools.get('rar',{}).get('sha256')} if rar else None
    corpus_pin=json.loads(mf.read_text())
    corpus_record={'source_manifest':str(mf),'source_manifest_sha256':sha(mf),
                   'revision':corpus_pin['revision'],'license_note':corpus_pin['license_note']}
    if pf:
        corpus_record.update(prepared_manifest=str(pf),prepared_manifest_sha256=sha(pf))
    payload={'schema':'mosaic-desktop-benchmark-v2','state':state,'invocation':[sys.executable,*sys.argv],'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'platform_scope':'macOS only','host_start':host_snapshot(),'tool_versions':tools,'rar_evaluation':rar_eval,'quiescence':gate,'corpus':corpus_record,'harness_sha256':sha(Path(__file__)), 'protocol':{'repeats':a.repeats,'warmups':1,'seed':SEED,'fsync':'archive file fsync after encode, outside timer; no durability timing claim','verification':'exact relative file paths, byte counts, SHA-256, and directory paths','rss':'wait4 per process; pipeline summed peaks are an upper bound, not simultaneous peak'},'cases':[],'randomized_order':orders,'warmup_records':warmups,'records':records,'summary':[],'failures':failures,'skipped_methods':skipped}
    try:
      with tempfile.TemporaryDirectory(prefix='mosaic-desktop-') as tmpname:
        tmp=Path(tmpname); syn=tmp/'synthetic'; syn.mkdir(); text_block=b'Mosaic desktop benchmark synthetic text fixture.\n'; (syn/'text.txt').write_bytes((text_block*((8*1024*1024+len(text_block)-1)//len(text_block)))[:8*1024*1024])
        (syn/'random.bin').write_bytes(random.Random(SEED).randbytes(8*1024*1024))
        smoke=tmp/'smoke'; smoke.mkdir(); (smoke/'tiny.txt').write_bytes(b'smoke fixture\n'*64); (smoke/'nested folder').mkdir(); (smoke/'nested folder'/'-report.txt').write_bytes(b'nested smoke\n'*17); (smoke/'empty').mkdir()
        textcase=tmp/'text-case'; textcase.mkdir(); shutil.move(str(syn/'text.txt'),textcase/'text.txt')
        randcase=tmp/'random-case'; randcase.mkdir(); shutil.move(str(syn/'random.bin'),randcase/'random.bin')
        cases=[('lz4-source','public LZ4 v1.10.0 source tree',lz),('synthetic-text-8m','generated repeated text 8 MiB',textcase),('synthetic-random-8m','generated pseudorandom 8 MiB seed '+str(SEED),randcase)]
        if a.allow_smoke: cases=[('synthetic-smoke','generated smoke fixture',smoke)]
        expected={cid:(tree(src) if src.is_dir() else [{'path':src.name,'bytes':src.stat().st_size,'sha256':sha(src)}],dirs(src) if src.is_dir() else []) for cid,_,src in cases}
        payload['cases']=[{'id':cid,'label':label,'input_bytes':sum(x['bytes'] for x in expected[cid][0]),'files':expected[cid][0],'directories':expected[cid][1]} for cid,label,_ in cases]
        for cid,label,src in cases:
          for phase in range(a.repeats+1):
            order=list(methods); rng.shuffle(order); orders.append({'case':cid,'phase':'warmup' if phase==0 else phase,'method_ids':[m['id'] for m in order]})
            for index,m in enumerate(order):
              wd=tmp/f'{cid}-{phase}-{index}'; wd.mkdir(); ext={'zip':'zip','7z':'7z','zstd':'tar.zst','gzip':'tar.gz','lz4':'tar.lz4'}.get(m.get('fmt') or m.get('codec'),'rar' if m['family']=='rar' else 'zip'); arc=wd/('archive.'+ext); err=wd/'encode.err'
              if m['family']=='bytepleat':
                cmd=[bp,'pack',src,'-o',arc,'--format',m['fmt'],'--threads','1','--deterministic']
                if m['fmt'] in ('zip','7z') or m['level']: cmd += ['--level',str(m['level'])]
                if m['fmt']=='7z': cmd += ['--dictionary','16777216','--solid']
                enc=run(cmd,ROOT,a.timeout,err)
              elif m['family']=='7zz':
                cmd=[zz,'a','-y','-bd','-t'+m['fmt'],'-mx='+str(m['level']),'-mmt=1']+(['-mm=Deflate'] if m['fmt']=='zip' else ['-m0=lzma2','-md=16m','-ms=on'])+[arc,src.name if src.is_file() else '.']
                enc=run(cmd,src.parent if src.is_file() else src,a.timeout,err)
              elif m['family']=='ditto': enc=run(['/usr/bin/ditto','-c','-k','--norsrc',src,arc],ROOT,a.timeout,err)
              elif m['family']=='infozip': enc=run(['/usr/bin/zip','-q','-r','-6',arc,'.'],src if src.is_dir() else src.parent,a.timeout,err)
              elif m['family']=='rar': enc=run([rar,'a','-r','-y','-cfg-','-ma5','-m'+str(m['level']),'-md16m','-s','-mt1',arc,src.name if src.is_file() else '.'],src.parent if src.is_file() else src,a.timeout,err)
              elif m['family']=='native-tar': enc=run(['/usr/bin/tar','--zstd','-cf',arc,'-C',str(src.parent),src.name],ROOT,a.timeout,err)
              else:
                tarcmd=['/usr/bin/tar','-cf','-','-C',str(src.parent if src.is_file() else src.parent),src.name if src.is_file() else src.name]
                if src.is_dir(): tarcmd=['/usr/bin/tar','-cf','-','-C',str(src.parent),src.name]
                comp={'zstd':['zstd','-3','-T1','-c','-'],'gzip':['gzip','-6','-c'],'lz4':['lz4','-c']}[m['codec']]
                enc=pipeline(tarcmd,[shutil.which(comp[0]),*comp[1:]],ROOT,a.timeout,wd/'tar.err',err,arc)
              item={'case_id':cid,'dataset':label,'synthetic':cid.startswith('synthetic'),'phase':'warmup' if phase==0 else 'measured','repeat':None if phase==0 else phase,'method':m,'encode':enc}
              if enc['exit_code']==0 and arc.is_file():
                with arc.open('rb') as f: os.fsync(f.fileno())
                item.update(archive_bytes_including_metadata_dictionary=arc.stat().st_size,archive_sha256=sha(arc)); dest=wd/'restore'
                if m['family']!='bytepleat': dest.mkdir()
                if m['family']=='bytepleat': dec=[bp,'unpack',arc,'-o',dest,'--max-output',str(sum(x['bytes'] for x in expected[cid][0])+2*1024*1024),'--max-dictionary','16777216']
                elif m['family']=='7zz': dec=[zz,'x','-y','-bd','-o'+str(dest),arc]
                elif m['family']=='ditto': dec=['/usr/bin/ditto','-x','-k',arc,dest]
                elif m['family']=='infozip': dec=['/usr/bin/unzip','-qq',arc,'-d',dest]
                elif m['family']=='rar': dec=[rar,'x','-y','-cfg-',arc,str(dest)+os.sep]
                elif m['family']=='native-tar': dec=['/usr/bin/tar','--zstd','-xf',arc,'-C',dest]
                else:
                  codec=m['codec']; decoder=[shutil.which(codec),'-d','-c',arc]
                  dr=pipeline(decoder,['/usr/bin/tar','-xf','-','-C',dest],ROOT,a.timeout,wd/'decode-codec.err',wd/'decode-tar.err',None,names=('decompressor','tar-extractor'))
                  dec=None
                if dec is not None: dr=run(dec,ROOT,a.timeout,wd/'decode.err')
                item['decode']=dr
                # Explicit expected layouts: 7zz/RAR/ditto store the named directory; other folder methods store its contents.
                restored=dest/src.name if m['family'] in ('native-tar','pipe') else dest
                try: ok=tree(restored)==expected[cid][0] and dirs(restored)==expected[cid][1]
                except Exception: ok=False
                item['verification']='pass' if ok and dr['exit_code']==0 else 'fail'
                if item['verification']!='pass': failures.append({'case':cid,'phase':item['phase'],'method':m,'verification':item['verification'],'decode':dr})
                if phase==0 and m['family'] in ('bytepleat','7zz') and m.get('fmt') in ('zip','7z'):
                  xd=wd/'cross-restore'
                  if m['family']=='bytepleat': xd.mkdir()
                  cross=([zz,'x','-y','-bd','-o'+str(xd),arc] if m['family']=='bytepleat' else [bp,'unpack',arc,'-o',xd,'--max-output',str(sum(x['bytes'] for x in expected[cid][0])+2*1024*1024),'--max-dictionary','16777216'])
                  xr=run(cross,ROOT,a.timeout,wd/'cross.err'); xv=tree(xd)==expected[cid][0] and dirs(xd)==expected[cid][1] if xr['exit_code']==0 else False
                  item['independent_warmup_decode']={'record':xr,'verification':'pass' if xv else 'fail'}
                  if not xv: failures.append({'case':cid,'phase':'warmup-cross-decode','method':m,'record':xr})
                if phase==0 and m['family']=='rar':
                  xd=wd/'independent-7zz-restore'; xd.mkdir(); xr=run([zz,'x','-y','-bd','-o'+str(xd),arc],ROOT,a.timeout,wd/'rar-7zz.err')
                  try: xv=xr['exit_code']==0 and tree(xd)==expected[cid][0] and dirs(xd)==expected[cid][1]
                  except Exception: xv=False
                  full_stderr=(wd/'rar-7zz.err').read_text(errors='replace')
                  independent_status=independent_decode_status(xr,xv,full_stderr)
                  item['independent_warmup_decode']={'decoder':'7zz','record':xr,'verification':independent_status}
                  if independent_status=='unsupported-method':
                    item['independent_warmup_decode']['diagnostics']=unsupported_method_diagnostics(full_stderr)
                  if independent_status=='fail': failures.append({'case':cid,'phase':'warmup-independent-7zz-restore','method':m,'record':xr})
              else:
                item.update(verification='encode-fail'); failures.append({'case':cid,'phase':item['phase'],'method':m,'encode':enc})
              (warmups if phase==0 else records).append(item)
              payload['state']='running'; atomic_checkpoint(out,payload)
    except BaseException as e:
      payload['state']='failed'; payload['fatal_error']=repr(e); payload['ended_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()); payload['elapsed_seconds']=time.time()-started; atomic_checkpoint(out,payload); raise
    groups={}
    for x in records:
      if x['verification']=='pass': groups.setdefault((x['case_id'],x['method']['id']),[]).append(x)
    for cid,_,_ in cases:
      for m in methods:
        xs=groups.get((cid,m['id']),[])
        if len(xs)!=a.repeats: failures.append({'case':cid,'method_id':m['id'],'type':'incomplete_group','verified_repeats':len(xs),'required_repeats':a.repeats})
        if xs: payload['summary'].append({'case_id':cid,'method_id':m['id'],'verified_repeats':len(xs),'required_repeats':a.repeats,'archive_bytes_median':statistics.median(x['archive_bytes_including_metadata_dictionary'] for x in xs),'encode_seconds_median':statistics.median(x['encode']['elapsed_seconds'] for x in xs),'decode_seconds_median':statistics.median(x['decode']['elapsed_seconds'] for x in xs)})
    payload['state']='smoke' if a.allow_smoke else ('failed' if failures else 'complete'); payload['ended_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()); payload['host_end']=host_snapshot(); payload['elapsed_seconds']=time.time()-started; payload['tool_sha256']={k:v.get('sha256') for k,v in tools.items()}; atomic_checkpoint(out,payload)
    print(json.dumps({'state':payload['state'],'warmups':len(warmups),'measured_records':len(records),'verified_measured':sum(x['verification']=='pass' for x in records),'failures':len(failures),'output':str(out)},indent=2)); return bool(failures)

if __name__=='__main__':
    try: raise SystemExit(int(main()))
    except (ValueError,OSError,RuntimeError) as e: sys.exit('error: '+str(e))
