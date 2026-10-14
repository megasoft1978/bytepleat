#!/usr/bin/env python3
"""Portable generated-fixture smoke and interoperability checks for Bytepleat."""
from __future__ import annotations
import argparse, hashlib, io, json, os, platform, random, shutil, subprocess, sys, tarfile, tempfile, time
from pathlib import Path

TIMEOUT = 45

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def file_sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20), b''): h.update(b)
    return h.hexdigest()

def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--binary', required=True); ap.add_argument('--output', required=True); ap.add_argument('--require-tools',action='store_true',help='fail if required native codecs or tar tooling are missing')
    a=ap.parse_args(); binary=Path(a.binary).resolve(); out=Path(a.output).resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    tools={n:shutil.which(n) for n in ('zstd','gzip','lz4','tar','bsdtar')}
    tools['7zz']=shutil.which('7zz') or shutil.which('7z')
    if not tools['7zz'] and os.name=='nt':
        for key in ('ProgramFiles','ProgramFiles(x86)'):
            candidate=Path(os.environ.get(key,''))/'7-Zip'/'7z.exe'
            if candidate.is_file():tools['7zz']=str(candidate);break
    report={'schema_version':1,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'platform':platform.platform(),'system':platform.system(),'machine':platform.machine(),'python':sys.version,'suite':str(Path(__file__).resolve()),'suite_sha256':file_sha(Path(__file__).resolve()),'binary':str(binary),'binary_sha256':file_sha(binary) if binary.is_file() else None,'native_tools':tools,'commands':[],'fixtures':[],'cases':[],'failures':[],'skips':[]}
    def save():
        report['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        report['totals']={'cases':len(report['cases']),'passed':sum(x['status']=='pass' for x in report['cases']),'failed':len(report['failures']),'skipped':len(report['skips'])}
        tmp=out.with_suffix(out.suffix+'.tmp'); tmp.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf8'); os.replace(tmp,out)
    def run(argv, data=None, rc=0):
        st=time.monotonic_ns()
        try: p=subprocess.run([str(x) for x in argv],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=TIMEOUT)
        except Exception as e:
            report['commands'].append({'argv':[str(x) for x in argv],'error':f'{type(e).__name__}: {e}'})
            raise
        row={'argv':[str(x) for x in argv],'returncode':p.returncode,'elapsed_ns':time.monotonic_ns()-st,'stdout_bytes':len(p.stdout),'stdout_sha256':sha(p.stdout),'stderr':p.stderr.decode('utf8','replace')[-2000:]}; report['commands'].append(row)
        if p.returncode!=rc: raise AssertionError(f"expected exit {rc}, got {p.returncode}: {row['stderr']}")
        return p.stdout
    def cli(*args,data=None,rc=0): return run([binary,*args],data,rc)
    def case(name,fn):
        try: details=fn(); report['cases'].append({'id':name,'status':'pass',**(details or {})})
        except Exception as e: report['cases'].append({'id':name,'status':'fail','error':f'{type(e).__name__}: {e}'}); report['failures'].append({'case':name,'error':str(e)})
        save()
    if not binary.is_file():
        report['failures'].append({'case':'setup','error':f'CLI binary unavailable: {binary}'}); save(); return 1
    if a.require_tools:
        missing=[x for x in ('zstd','gzip','lz4') if not tools[x]]
        if not (tools['tar'] or tools['bsdtar']): missing.append('tar/bsdtar')
        if not tools['7zz']: missing.append('7zz/7z')
        if missing: report['failures'].append({'case':'required-tools','error':'missing required tools: '+', '.join(missing)}); save(); return 1
    rng=random.Random(0x4d4f5341)
    payloads={'empty':b'','random':rng.randbytes(131071),'repetitive':b'abracadabra\0'*8192}
    # Keep fixture paths short even when the report lives in a deeply nested
    # verifier temp directory (notably on Windows). Report placement is separate.
    with tempfile.TemporaryDirectory(prefix='bp-smoke-') as td:
        t=Path(td)
        for label,data in payloads.items():
            for fmt in ('zstd','gzip','lz4'):
                def pipe(label=label,data=data,fmt=fmt):
                    enc=cli('compress','-','-o','-','--format',fmt,'--quiet',data=data)
                    got=cli('decompress','-','-o','-','--quiet',data=enc)
                    assert got==data, 'pipe roundtrip differs byte-for-byte'
                    return {'format':fmt,'fixture':label,'input_bytes':len(data),'input_sha256':sha(data),'output_bytes':len(got),'output_sha256':sha(got)}
                case(f'pipe:{label}:{fmt}',pipe)
        vectors={}
        for typ,width,signed in [('i32',4,True),('u32',4,False),('i64',8,True),('u64',8,False)]:
            vals=range(-5000,5000) if signed else range(10000)
            vectors[typ]=b''.join(int(v).to_bytes(width,'little',signed=signed) for v in vals)
        vectors['f32']=b''.join(v.to_bytes(4,'little') for v in [0,0x80000000,0x7f800000,0xff800000,0x7fc12345]+[rng.getrandbits(32) for _ in range(3000)])
        vectors['f64']=b''.join(v.to_bytes(8,'little') for v in [0,0x8000000000000000,0x7ff0000000000000,0xfff0000000000000,0x7ff8123456789abc]+[rng.getrandbits(64) for _ in range(3000)])
        for typ in ('i32','u32','i64','u64','f32','f64'): vectors[typ+'-empty']=b''
        for name,data in vectors.items():
            typ=name.split('-',1)[0]; src=t/(name+'.raw'); packed=t/(name+'.pco'); src.write_bytes(data)
            def pco(typ=typ,data=data,src=src,packed=packed):
                cli('compress',str(src),'--format','pco','--type',typ,'-o',str(packed),'--quiet'); cli('test',str(packed),'--type',typ)
                got=cli('decompress',str(packed),'--type',typ,'-o','-','--quiet'); assert got==data, 'typed Pco bits differ'
                return {'format':'pco','type':typ,'bytes':len(data),'sha256':sha(got)}
            case('pco:'+name,pco)
        def safety():
            raw=t/'source.bin'; packed=t/'source.gz'; dest=t/'protected'; raw.write_bytes(b'protect me'*1000)
            cli('compress',str(raw),'-o',str(packed),'--format','gzip','--quiet')
            dest.write_bytes(b'existing'); cli('decompress',str(packed),'-o',str(dest),'--quiet',rc=1); assert dest.read_bytes()==b'existing'
            cli('decompress',str(packed),'-o',str(dest),'--force','--max-output','4','--quiet',rc=1); assert dest.read_bytes()==b'existing'
            cli('decompress',str(packed),'-o',str(dest),'--force','--quiet'); assert dest.read_bytes()==raw.read_bytes()
            try: cli('compress',str(packed),'-o',str(packed),'--format','gzip','--force','--quiet',rc=1)
            except AssertionError: raise
            return {'no_clobber':True,'failed_force_preserved_existing':True,'alias_input_rejected':True}
        case('output-safety',safety)
        # Native codec interop is independently recorded for every installed tool.
        for fmt,tool,enc,dec in [('gzip','gzip',['-n','-6','-c'],['-d','-c']),('zstd','zstd',['-q','-3','-T1','-c'],['-q','-d','-c']),('lz4','lz4',['-B4','-BX','-c'],['-d','-c'])]:
            if not tools[tool]: report['skips'].append({'case':'native-codec:'+fmt,'reason':f'{tool} not installed'}); continue
            def interop(fmt=fmt,tool=tool,enc=enc,dec=dec):
                data=payloads['repetitive']; native=run([tools[tool],*enc],data=data); got=cli('decompress','-','-o','-','--quiet',data=native); assert got==data
                encoded=cli('compress','-','-o','-','--format',fmt,'--quiet',data=data); assert run([tools[tool],*dec],data=encoded)==data
                return {'format':fmt,'tool':tools[tool],'bytes':len(data),'sha256':sha(data)}
            case('native-codec:'+fmt,interop)
        # Standard tar archive creation/extraction: fixtures are generated locally.
        tarpath=tools['bsdtar'] or tools['tar']
        if tarpath:
            def tar_case():
                root=t/'tree'; (root/'unicode-東京').mkdir(parents=True); (root/'unicode-東京'/'hello.txt').write_bytes(b'hello\n'); (root/('long-'+'n'*110)).write_bytes(b'long')
                plain=t/'tree.tar'; run([tarpath,'-cf',plain,'-C',root,'.'])
                # Native tar consumes Bytepleat's standard gzip stream.
                bytepleat_arc=t/'tree.tar.gz'; cli('compress',str(plain),'-o',str(bytepleat_arc),'--format','gzip','--quiet')
                native_out=t/'native-out'; native_out.mkdir(); decompressed=run([tools['gzip'],'-d','-c',bytepleat_arc]) if tools['gzip'] else cli('decompress',str(bytepleat_arc),'-o','-','--quiet')
                decoded=t/'decoded.tar'; decoded.write_bytes(decompressed); run([tarpath,'-xf',decoded,'-C',native_out]); assert (native_out/'./unicode-東京'/'hello.txt').read_bytes()==b'hello\n'
                # Bytepleat consumes a native tar archive after native gzip encoding.
                native_gz=t/'native.tar.gz'; native_gz.write_bytes(run([tools['gzip'],'-n','-c'],data=plain.read_bytes()) if tools['gzip'] else cli('compress',str(plain),'-o','-','--format','gzip','--quiet'))
                dest=t/'extract'; cli('unpack',str(native_gz),'-o',str(dest)); assert (dest/'unicode-東京'/'hello.txt').read_bytes()==b'hello\n'
                return {'tar_tool':tarpath,'unicode_and_long_names':True,'bidirectional':True}
            case('standard-tar-unpack',tar_case)
        else: report['skips'].append({'case':'standard-tar-unpack','reason':'no native tar/bsdtar installed'})
        # Corrupt archive rejection, path traversal and entry cap use hostile generated tar only.
        def make_tar(entries):
            b=io.BytesIO()
            with tarfile.open(fileobj=b,mode='w',format=tarfile.PAX_FORMAT) as tf:
                for name,body in entries:
                    ti=tarfile.TarInfo(name); ti.size=len(body); tf.addfile(ti,io.BytesIO(body))
            return b.getvalue()+b'\0'*1024
        def hostile():
            # Symbolic and hard links are deliberately hostile; they must never be materialized.
            symlink=io.BytesIO()
            with tarfile.open(fileobj=symlink,mode='w',format=tarfile.PAX_FORMAT) as tf:
                ti=tarfile.TarInfo('link'); ti.type=tarfile.SYMTYPE; ti.linkname='../escape'; tf.addfile(ti)
            hardlink=io.BytesIO()
            with tarfile.open(fileobj=hardlink,mode='w',format=tarfile.PAX_FORMAT) as tf:
                ti=tarfile.TarInfo('link'); ti.type=tarfile.LNKTYPE; ti.linkname='../escape'; tf.addfile(ti)
            good=make_tar([('safe',b'x')]); corrupt=bytearray(good); corrupt[0]^=1
            for label,blob,extra in [('traversal',make_tar([('../escape',b'x')]),[]),('symlink',symlink.getvalue()+b'\0'*1024,[]),('hardlink',hardlink.getvalue()+b'\0'*1024,[]),('count',make_tar([('a',b'a'),('b',b'b')]),['--max-entries','1']),('deep-path',make_tar([('/'.join(['d']*8)+'/file',b'x')]),['--max-depth','2']),('bad-checksum',bytes(corrupt),[]),('appended-after-end',good+make_tar([('extra',b'z')]),[]),('missing-end',good[:1024],[]),('one-end-block',good[:1536],[])]:
                arc=t/(label+'.gz'); arc.write_bytes(cli('compress','-','-o','-','--format','gzip','--quiet',data=blob)); dest=t/('dest-'+label); cli('unpack',str(arc),'-o',str(dest),*extra,rc=1); assert not dest.exists(),f'{label} published output'
            if os.name=='nt':
                arc=t/'case-collision.gz'; arc.write_bytes(cli('compress','-','-o','-','--format','gzip','--quiet',data=make_tar([('Name',b'a'),('name',b'b')]))); dest=t/'dest-case-collision'; cli('unpack',str(arc),'-o',str(dest),rc=1); assert not dest.exists()
            return {'hostile_fixtures':['traversal','symlink','hardlink','entry-cap','depth-limit','bad-checksum','appended-after-end-marker','missing-end-marker','one-end-block'],'windows_case_collision_checked':os.name=='nt','no_output_published':True}
        case('hostile-tar-rejection',hostile)
        def codec_failures():
            data=payloads['repetitive']
            for fmt in ('zstd','gzip','lz4'):
                encoded=cli('compress','-','-o','-','--format',fmt,'--quiet',data=data)
                cli('test','-','--max-output','16',data=encoded,rc=1)
                cli('test','-',data=encoded[:-1],rc=1)
                corrupt=bytearray(encoded);corrupt[-5]^=0x40
                cli('test','-',data=bytes(corrupt),rc=1)
                cli('test','-',data=encoded+b'not-a-frame',rc=1)
            return {'formats':['zstd','gzip','lz4'],'checks':['output-cap','truncation','checksum-corruption','trailing-junk']}
        case('codec-failure-policy',codec_failures)
        # Report all fixture identities/hashes, including generated binary streams.
        report['fixtures']=[{'name':k,'bytes':len(v),'sha256':sha(v),'synthetic':True} for k,v in payloads.items()]+[{'name':k,'bytes':len(v),'sha256':sha(v),'synthetic':True,'type':k.split('-',1)[0]} for k,v in vectors.items()]
    save(); print(json.dumps(report['totals'],sort_keys=True)); return 1 if report['failures'] else 0
if __name__=='__main__': sys.exit(main())
