#!/usr/bin/env python3
"""Generated-fixture independent ZIP/7z interoperability checks for Arqlet."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, random, shutil, struct, subprocess, sys, tempfile, time, zipfile
from pathlib import Path


def sha(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def snapshot(root: Path) -> dict:
    files={}; dirs=[]
    for p in sorted(root.rglob('*'),key=lambda x:x.relative_to(root).as_posix()):
        rel=p.relative_to(root).as_posix()
        if p.is_symlink(): raise ValueError('fixture unexpectedly contains symlink')
        if p.is_dir(): dirs.append(rel)
        elif p.is_file(): files[rel]={'bytes':p.stat().st_size,'sha256':sha(p)}
    return {'files':files,'directories':dirs,'file_bytes':sum(x['bytes'] for x in files.values()),'encoded_entry_bytes':None}

def run(argv, timeout=60):
    p=subprocess.run([str(x) for x in argv],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    return {'argv':[str(x) for x in argv],'exit_code':p.returncode,'stdout':p.stdout.decode('utf-8','replace')[-4000:],'stderr':p.stderr.decode('utf-8','replace')[-4000:]}

def record(results, name, fn):
    r={'name':name,'status':'pass','evidence':{}}
    try: r['evidence']=fn()
    except Exception as e: r.update(status='fail',error=f'{type(e).__name__}: {e}')
    results.append(r)

def fixture(root: Path):
    (root/'empty').mkdir(parents=True); (root/'nested'/'deep').mkdir(parents=True)
    (root/'nested'/'deep'/'zero.bin').write_bytes(b'\0'*8192)
    (root/'nested'/('utf8-long-'+('segment-'*14)+'é.txt')).write_text('UTF-8 test\n' * 137,encoding='utf-8')
    (root/'empty-file').write_bytes(b'')
    (root/'random.bin').write_bytes(random.Random(731).randbytes(16384))
    (root/'multi').mkdir(); (root/'multi'/'a').write_bytes(b'ABCD'*4096); (root/'multi'/'b').write_bytes(b'ABCD'*4096)

def zip_raw(name: bytes, data=b'x', mode=0o100644):
    # Produce a minimal raw-path ZIP member using zipfile's supported byte names.
    import io
    o=io.BytesIO(); z=zipfile.ZipFile(o,'w',zipfile.ZIP_STORED)
    i=zipfile.ZipInfo(); i.filename=name.decode('cp437'); i.create_system=3; i.external_attr=(mode<<16)
    z.writestr(i,data); z.close(); return o.getvalue()

def zip_many(entries):
    import io
    o=io.BytesIO(); z=zipfile.ZipFile(o,'w',zipfile.ZIP_STORED)
    for name,data,mode in entries:
        i=zipfile.ZipInfo(name); i.create_system=3; i.external_attr=(mode<<16); z.writestr(i,data)
    z.close(); return o.getvalue()

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--binary',required=True); ap.add_argument('--native7z',required=True); ap.add_argument('--output',required=True)
    a=ap.parse_args(); out=Path(a.output).resolve()
    if out.exists(): ap.error(f'refusing to overwrite {out}')
    binary=Path(a.binary).resolve(); native=Path(a.native7z).resolve()
    if not binary.is_file() or not native.is_file(): ap.error('binary and native7z must exist')
    results=[]; commands=[]; started=time.time()
    binary_version=run([binary,'--version'])
    commands.append(binary_version)
    with tempfile.TemporaryDirectory(prefix='arqlet-archive-validation-') as td:
        t=Path(td); source=t/'source'; source.mkdir(); fixture(source); expected=snapshot(source)
        native_version=run([native,'i'])
        commands.append(native_version)
        record(results,'fixture_manifest',lambda:expected)
        # Candidate-generated formats; extraction by Python zip and independent 7zz.
        for fmt, opts in [('zip',['--stored']),('zip',[]),('7z',['--solid']),('7z',['--no-solid'])]:
            tag=fmt+('-stored' if '--stored' in opts else '-deflate' if fmt=='zip' else opts[0][2:])
            arc=t/(tag+('.zip' if fmt=='zip' else '.7z')); dest=t/(tag+'-out')
            def candidate(fmt=fmt,opts=opts,arc=arc,dest=dest):
                c=run([binary,'pack',source,'--format',fmt,'--level','5',*(['--dictionary','16777216'] if fmt=='7z' else []),*opts,'--threads','1','--deterministic','-o',arc]); commands.append(c)
                if c['exit_code']: raise RuntimeError('candidate pack failed: '+c['stderr'])
                if not arc.exists(): raise RuntimeError('pack produced no archive')
                sz=arc.stat().st_size; dest.mkdir()
                if fmt=='zip':
                    with zipfile.ZipFile(arc) as z: z.extractall(dest)
                else:
                    x=run([native,'x','-y','-bd',f'-o{dest}',arc]); commands.append(x)
                    if x['exit_code']: raise RuntimeError('native extraction failed: '+x['stderr'])
                got=snapshot(dest)
                if got['files']!=expected['files'] or got['directories']!=expected['directories']: raise RuntimeError('independent extraction differs from source manifest')
                got['encoded_entry_bytes']=sz
                if fmt=='zip':
                    native_dest=t/(tag+'-native-out'); n=run([native,'x','-y','-bd',f'-o{native_dest}',arc]); commands.append(n)
                    if n['exit_code']: raise RuntimeError('native 7zz could not read candidate ZIP: '+n['stderr'])
                    native_got=snapshot(native_dest)
                    if native_got['files']!=expected['files'] or native_got['directories']!=expected['directories']: raise RuntimeError('native 7zz ZIP extraction differs from source manifest')
                # Candidate's own test/info are diagnostic only, never validation of itself.
                ctest=run([binary,'test',arc]); commands.append(ctest)
                ci=run([binary,'info',arc,'--json']); commands.append(ci)
                if ctest['exit_code'] or ci['exit_code']: raise RuntimeError(f'candidate test/info failed: test={ctest["exit_code"]}, info={ci["exit_code"]}')
                try: info_json=json.loads(ci['stdout'])
                except Exception as e: raise RuntimeError(f'candidate info --json did not return JSON: {e}')
                return {'format':fmt,'size_with_headers_and_metadata':sz,'restored':got,'native7zz_zip_read':fmt=='zip','candidate_test_exit':ctest['exit_code'],'candidate_info_exit':ci['exit_code'],'info_json':info_json,'integrity_validated':False}
            record(results,'candidate-'+tag,candidate)
        # Independently generated native 7z archives must be readable by Mosaic.
        for solid in (True,False):
            arc=t/f'native-{solid}.7z'
            # shell expansion is deliberately avoided; 7zz receives concrete relative paths.
            arg=['a','-t7z','-m0=lzma2','-md=16m','-mmt=1','-ms=on' if solid else '-ms=off',arc,*[p.relative_to(source) for p in sorted(source.iterdir())]]
            # Use cwd for safe generated fixture paths.
            p=subprocess.run([str(native),*map(str,arg)],cwd=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            commands.append({'argv':[str(native),*map(str,arg)],'exit_code':p.returncode,'stdout':p.stdout.decode('utf8','replace')[-2000:],'stderr':p.stderr.decode('utf8','replace')[-2000:]})
            def read_native(arc=arc,solid=solid):
                dest=t/f'native-read-{solid}'; c=run([binary,'unpack',arc,'-o',dest,'--max-output','1000000','--max-entries','100','--max-depth','20','--max-dictionary','16777216','--max-header','1048576']); commands.append(c)
                if c['exit_code']: raise RuntimeError('candidate rejected native 7z: '+c['stderr'])
                got=snapshot(dest)
                if got['files']!=expected['files'] or got['directories']!=expected['directories']: raise RuntimeError('candidate native 7z extraction differs')
                return {'native_archive_sha256':sha(arc),'restored':got,'integrity_validated':False}
            record(results,'native-7z-read-'+str(solid),read_native)
        # Python's ZIP writer provides an independent ZIP corpus for Mosaic.
        pyzip=t/'python.zip'
        with zipfile.ZipFile(pyzip,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(source.rglob('*')):
                rel=p.relative_to(source).as_posix()
                if p.is_dir(): z.writestr(rel+'/',b'')
                else: z.write(p,rel)
        dest=t/'python-zip-read'; c=run([binary,'unpack',pyzip,'-o',dest,'--max-output','1000000','--max-entries','100','--max-depth','20','--max-dictionary','16777216','--max-header','1048576']); commands.append(c)
        def python_zip_read():
            if c['exit_code']:raise RuntimeError('candidate rejected Python Deflate ZIP: '+c['stderr'])
            got=snapshot(dest)
            if got['files']!=expected['files'] or got['directories']!=expected['directories']:raise RuntimeError('candidate Python ZIP extraction differs')
            return {'input_archive_sha256':sha(pyzip),'restored':got,'integrity_validated':False}
        record(results,'python-deflate-zip-read',python_zip_read)
        native_zip=t/'native-deflate.zip'
        # Arqlet accepts ASCII names or UTF-8-flagged UTF-8 names; force 7-Zip
        # to encode non-ASCII ZIP names as UTF-8 instead of the Windows codepage.
        native_args=['a','-tzip','-mm=Deflate','-mx=6','-mmt=1','-mcu=on',native_zip,*[p.relative_to(source) for p in sorted(source.iterdir())]]
        np=subprocess.run([str(native),*map(str,native_args)],cwd=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        commands.append({'argv':[str(native),*map(str,native_args)],'exit_code':np.returncode,'stdout':np.stdout.decode('utf8','replace')[-2000:],'stderr':np.stderr.decode('utf8','replace')[-2000:]})
        def native_zip_read():
            if np.returncode:raise RuntimeError('native 7zz ZIP creation failed')
            nd=t/'native-zip-read';c=run([binary,'unpack',native_zip,'-o',nd,'--max-output','1000000','--max-entries','100','--max-depth','20','--max-dictionary','16777216','--max-header','1048576']);commands.append(c)
            if c['exit_code']:raise RuntimeError('candidate rejected native Deflate ZIP: '+c['stderr'])
            got=snapshot(nd)
            if got['files']!=expected['files'] or got['directories']!=expected['directories']:raise RuntimeError('candidate native ZIP extraction differs')
            return {'input_archive_sha256':sha(native_zip),'restored':got,'integrity_validated':False}
        record(results,'native-deflate-zip-read',native_zip_read)
        # Negative raw ZIP fixtures: CRC, truncation, trailing bytes, traversal and symlink.
        valid=t/'valid.zip'
        with zipfile.ZipFile(valid,'w',zipfile.ZIP_STORED) as z:z.writestr('ok','payload')
        raw=valid.read_bytes();
        bads={'truncated':raw[:-8],'trailing':raw+b'extra','crc':raw.replace(b'payload',b'PAYLOAD',1),'traversal':zip_raw(b'../escape'),'symlink':zip_raw(b'link',mode=0o120777),'absolute':zip_raw(b'/absolute'),'drive':zip_raw(b'C:/drive'),'parent-alias':zip_raw(b'a/../b'),
              'exact-duplicate':zip_many([('same',b'a',0o100644),('same',b'b',0o100644)]),
              'case-collision':zip_many([('Name',b'a',0o100644),('name',b'b',0o100644)]),
              'nfc-collision':zip_many([('caf\u00e9',b'a',0o100644),('cafe\u0301',b'b',0o100644)]),
              'file-directory-prefix':zip_many([('node',b'a',0o100644),('node/child',b'b',0o100644)]),
              'entry-limit':zip_many([('one',b'a',0o100644),('two',b'b',0o100644)]),
              'depth-limit':zip_many([('a/b/c',b'x',0o100644)]),
              'output-limit':zip_many([('large',b'x'*64,0o100644)])}
        for name,data in bads.items():
            arc=t/(name+'.zip');arc.write_bytes(data);dest=t/('reject-'+name)
            def rejected(arc=arc,dest=dest):
                entries='1' if arc.stem=='entry-limit' else '100'
                c=run([binary,'unpack',arc,'-o',dest,'--max-output','32','--max-entries',entries,'--max-depth','2','--max-dictionary','16777216','--max-header','1048576']);commands.append(c)
                if c['exit_code']==0: raise RuntimeError('malicious/corrupt archive accepted')
                if dest.exists(): raise RuntimeError('destination published after rejected archive')
                return {'exit_code':c['exit_code'],'destination_absent':True}
            record(results,'reject-'+name,rejected)
        # The initial supported subset excludes ZIP64 and non-Deflate codecs.
        zip64=t/'zip64-local-header.zip'
        with zipfile.ZipFile(zip64,'w',allowZip64=True) as z:
            with z.open('tiny',mode='w',force_zip64=True) as f:f.write(b'zip64')
        bzip=t/'bzip2.zip'
        with zipfile.ZipFile(bzip,'w',compression=zipfile.ZIP_BZIP2) as z:z.writestr('tiny',b'bzip2')
        for name,arc in [('unsupported-bzip2-rejection',bzip)]:
            dest=t/name
            def reject_feature(arc=arc,dest=dest):
                c=run([binary,'unpack',arc,'-o',dest,'--max-output','100','--max-entries','10','--max-depth','10','--max-dictionary','16777216','--max-header','1048576']);commands.append(c)
                if c['exit_code']==0 or dest.exists():raise RuntimeError('unsupported ZIP feature was not rejected without publication')
                return {'explicit_rejection_exit':c['exit_code'],'destination_absent':True}
            record(results,'expected-'+name,reject_feature)
        def zip64_behavior():
            dest=t/'zip64-behavior';c=run([binary,'unpack',zip64,'-o',dest,'--max-output','100','--max-entries','10','--max-depth','10','--max-dictionary','16777216','--max-header','1048576']);commands.append(c)
            if c['exit_code']:
                if dest.exists():raise RuntimeError('ZIP64 rejection published output')
                return {'behavior':'explicitly-rejected','exit_code':c['exit_code'],'destination_absent':True}
            got=snapshot(dest)
            if got['files']!={'tiny':{'bytes':5,'sha256':hashlib.sha256(b'zip64').hexdigest()}}:raise RuntimeError('accepted ZIP64 output did not restore exact bytes')
            return {'behavior':'supported-and-byte-verified','restored':got}
        record(results,'zip64-policy',zip64_behavior)
        # Password fixture generation is intentionally skipped; stdlib ZIP has no encrypted writer.
        for fmt in ('zip','7z'):
            enc=t/('encrypted.'+fmt)
            argv=[native,'a','-t'+fmt,'-pfixture-password',enc,source/'random.bin']
            if fmt=='zip':argv+=['-mem=AES256']
            else:argv+=['-mhe=on']
            generated=run(argv);commands.append(generated)
            def encrypted_reject(enc=enc,fmt=fmt,generated=generated):
                if generated['exit_code']:raise RuntimeError('fixture creation failed: '+generated['stderr'])
                dest=t/('encrypted-destination-'+fmt);r=run([binary,'unpack',enc,'-o',dest]);commands.append(r)
                if r['exit_code']==0 or dest.exists():raise RuntimeError('encrypted archive was accepted or published')
                return {'exit_code':r['exit_code'],'destination_absent':True,'generated_fixture_sha256':sha(enc)}
            record(results,'encrypted-'+fmt+'-rejection',encrypted_reject)
        # Small-header-limit input made from a large count of generated native entries.
        many=t/'many-generated';many.mkdir()
        for i in range(120):(many/f'item-{i:03}.txt').write_bytes((f'generated {i}\n').encode())
        header7=t/'generated-many-entries.7z';p=subprocess.run([str(native),'a','-t7z','-m0=lzma2','-md=16m','-mmt=1',str(header7),*[str(x) for x in sorted(many.iterdir())]],cwd=many,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        commands.append({'argv':[str(native),'a','-t7z','-m0=lzma2','-md=16m','-mmt=1',str(header7),'120 generated entries'],'exit_code':p.returncode,'stderr':p.stderr.decode('utf8','replace')[-2000:]})
        if p.returncode==0:
            def header_reject():
                dest=t/'reject-header';c=run([binary,'unpack',header7,'-o',dest,'--max-output','100000','--max-entries','1000','--max-depth','10','--max-dictionary','16777216','--max-header','64']);commands.append(c)
                if c['exit_code']==0 or dest.exists():raise RuntimeError('7z header limit was not enforced before publication')
                return {'explicit_rejection_exit':c['exit_code'],'destination_absent':True,'archive_bytes':header7.stat().st_size}
            record(results,'7z-header-limit',header_reject)
        # Native 7z CRC/dictionary bounds use only generated bytes and upstream 7zz.
        large7=t/'generated-64m-dictionary.7z'
        p=subprocess.run([str(native),'a','-t7z','-m0=lzma2','-md=64m','-mmt=1',str(large7),str(source/'random.bin')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        commands.append({'argv':[str(native),'a','-t7z','-m0=lzma2','-md=64m','-mmt=1',str(large7),str(source/'random.bin')],'exit_code':p.returncode,'stderr':p.stderr.decode('utf8','replace')[-2000:]})
        if p.returncode==0:
            def dictionary_reject():
                dest=t/'reject-dictionary';c=run([binary,'unpack',large7,'-o',dest,'--max-output','100000','--max-entries','10','--max-depth','10','--max-dictionary','1024','--max-header','1048576']);commands.append(c)
                if c['exit_code']==0 or dest.exists():raise RuntimeError('dictionary limit was not enforced before publication')
                return {'explicit_rejection_exit':c['exit_code'],'destination_absent':True,'archive_sha256':sha(large7)}
            record(results,'7z-dictionary-limit',dictionary_reject)
            tampered=t/'tampered-7z.7z';raw7=bytearray(large7.read_bytes());raw7[len(raw7)//2]^=0x40;tampered.write_bytes(raw7)
            def sevenz_corrupt_reject():
                native_test=run([native,'t',tampered]);commands.append(native_test)
                if native_test['exit_code']==0:raise RuntimeError('native 7zz test did not recognize the byte-tampered fixture as corrupt')
                dest=t/'reject-7z-corrupt';c=run([binary,'unpack',tampered,'-o',dest,'--max-output','100000','--max-entries','10','--max-depth','10','--max-dictionary','67108864','--max-header','1048576']);commands.append(c)
                if c['exit_code']==0 or dest.exists():raise RuntimeError('tampered native 7z unexpectedly accepted')
                return {'rejected':True,'destination_absent':True,'tampered_sha256':sha(tampered),'native_7zz_rejection':native_test['stdout']+'\n'+native_test['stderr']}
            record(results,'7z-tamper-rejection',sevenz_corrupt_reject)
        # No external parser can meaningfully test all bounds; exercise candidate limits and no-overwrite.
        # Preserve an existing destination byte-for-byte.
        ex=t/'existing';ex.mkdir();(ex/'sentinel').write_bytes(b'unchanged')
        c=run([binary,'unpack',pyzip,'-o',ex]);commands.append(c)
        record(results,'existing-destination-untouched',lambda:{'rejected':c['exit_code']!=0,'sentinel_sha256':sha(ex/'sentinel')} if c['exit_code'] and sha(ex/'sentinel')==hashlib.sha256(b'unchanged').hexdigest() else (_ for _ in ()).throw(RuntimeError('existing destination changed or accepted')))
    payload={'schema':'arqlet-archive-validation-v1','timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'platform':platform.platform(),'machine':platform.machine(),'binary':str(binary),'binary_sha256':sha(binary),'binary_version':binary_version['stdout'].strip(),'native7z':str(native),'native7z_sha256':sha(native),'native7z_version':native_version['stdout'].splitlines()[1:3],'suite_sha256':sha(Path(__file__)),'commands':commands,'results':results,'summary':{'pass':sum(r['status']=='pass' for r in results),'fail':sum(r['status']=='fail' for r in results),'skipped':sum(r['status']=='skipped' for r in results),'duration_seconds':round(time.time()-started,3)}}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload['summary'],indent=2)); return 1 if payload['summary']['fail'] else 0
if __name__=='__main__': raise SystemExit(main())
