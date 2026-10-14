#!/usr/bin/env python3
"""Validate Bytepleat release archives before extraction or native execution."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, stat, struct, subprocess, sys, tarfile, tempfile, zipfile
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
TARGETS={"aarch64-apple-darwin":("tar.gz","bytepleat"),"x86_64-unknown-linux-gnu":("tar.gz","bytepleat"),"x86_64-pc-windows-msvc":("zip","bytepleat.exe")}
REQUIRED={"Cargo.toml","README.md","RELEASE.md","LICENSE","Cargo.lock","THIRD-PARTY.json","BUILD-INFO.json"}
MAX_ARCHIVE=128*1024*1024;MAX_MEMBERS=4096;MAX_TOTAL=512*1024*1024;MAX_MEMBER=128*1024*1024
def sha_bytes(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def sha_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def safe_name(s:str)->str:
    if "\\" in s or "\x00" in s: raise ValueError(f"unsafe archive path: {s!r}")
    pieces=s.split("/");p=PurePosixPath(s)
    if p.is_absolute() or not p.parts or any(x in ("", ".", "..") or ":" in x or x.rstrip(" .")!=x or any(c in x for c in '<>"|?*') for x in pieces): raise ValueError(f"unsafe archive path: {s!r}")
    return p.as_posix()
def preflight_zip(path:Path)->None:
    """Bound central-directory parsing before zipfile materializes ZipInfo rows."""
    size=path.stat().st_size
    with path.open("rb") as f:
        f.seek(max(0,size-65557));tail=f.read()
        pos=tail.rfind(b"PK\x05\x06")
        if pos<0 or pos+22>len(tail):raise ValueError("missing ZIP end record")
        disk,cd_disk,on_disk,total,cd_size,cd_offset,comment=struct.unpack_from("<HHHHIIH",tail,pos+4)
        eocd= max(0,size-65557)+pos
        if eocd+22+comment!=size or disk or cd_disk or on_disk!=total:raise ValueError("unsupported or inconsistent ZIP directory")
        if total in (0xffff,) or cd_size==0xffffffff or cd_offset==0xffffffff:raise ValueError("ZIP64 release archives are not supported")
        if total>MAX_MEMBERS:raise ValueError("archive exceeds 4096 member limit")
        if cd_offset+cd_size>eocd:raise ValueError("ZIP central directory exceeds archive bounds")
        f.seek(cd_offset);end=cd_offset+cd_size
        for _ in range(total):
            fixed=f.read(46)
            if len(fixed)!=46 or fixed[:4]!=b"PK\x01\x02":raise ValueError("invalid ZIP central directory record")
            name_len,extra_len,comment_len=struct.unpack_from("<HHH",fixed,28)
            skip=name_len+extra_len+comment_len
            if f.tell()+skip>end:raise ValueError("ZIP central directory record exceeds declared bounds")
            f.seek(skip,os.SEEK_CUR)
        if f.tell()!=end:raise ValueError("ZIP central directory size mismatch")
def iter_notices(inventory:dict):
    for collection in ("packages","runtime_components"):
        items=inventory.get(collection,[])
        if not isinstance(items,list):raise ValueError(f"inventory {collection} must be an array")
        for item in items:
            if not isinstance(item,dict):raise ValueError("invalid inventory component")
            for field in ("notices","vendored_component_notices"):
                rows=item.get(field,[])
                if not isinstance(rows,list):raise ValueError(f"inventory {field} must be an array")
                for row in rows:
                    if not isinstance(row,dict) or not isinstance(row.get("path"),str) or not re.fullmatch(r"[0-9a-f]{64}",str(row.get("sha256",""))):raise ValueError("invalid notice path or SHA-256")
                    path=safe_name(row["path"])
                    if not path.startswith("third-party-licenses/"):raise ValueError("inventory notice escapes license directory")
                    yield row
def expected(root:str, exe:str, inventory:dict)->set[str]:
    files={f"{root}/{x}" for x in REQUIRED}|{f"{root}/{exe}",f"{root}/THIRD-PARTY-{inventory.get('target')}.json"}
    def add_notice(n):
        path=n.get("path")
        if path:
            p=safe_name(path)
            if not p.startswith("third-party-licenses/"): raise ValueError("inventory notice escapes license directory")
            files.add(f"{root}/{p}")
    for notice in iter_notices(inventory):add_notice(notice)
    # Directory entries are optional in ZIP/tar; regular-file set is exact.
    return files
def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive",required=True,type=Path);ap.add_argument("--target",required=True,choices=sorted(TARGETS));ap.add_argument("--version",required=True);ap.add_argument("--revision",required=True)
    ap.add_argument("--native",action="store_true",help="required to execute the archive binary on this runner")
    ap.add_argument("--native7z",type=Path);ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();archive=a.archive.resolve();out=a.output.resolve();ext,exe=TARGETS[a.target];asset=f"bytepleat-{a.version}-{a.target}.{ext}";root=f"bytepleat-{a.version}-{a.target}"
    if not re.fullmatch(r"\d+\.\d+\.\d+",a.version) or not re.fullmatch(r"[0-9a-f]{40,64}",a.revision):ap.error("invalid requested version or revision")
    if archive.name!=asset:ap.error("archive filename does not match requested version and target")
    if out.exists():ap.error("refusing to overwrite verification report")
    if not archive.is_file():ap.error("archive does not exist")
    if archive.stat().st_size>MAX_ARCHIVE:ap.error("compressed archive exceeds 128 MiB limit")
    digest=sha_file(archive); sidecar=archive.with_name(archive.name+".sha256")
    if not sidecar.is_file() or sidecar.read_text(encoding="ascii").strip()!=f"{digest}  {asset}":ap.error("archive SHA-256 sidecar is missing or incorrect")
    if a.native and a.target not in {"aarch64-apple-darwin" if sys.platform=="darwin" and __import__('platform').machine().lower() in ("arm64","aarch64") else "x86_64-unknown-linux-gnu" if sys.platform=="linux" and __import__('platform').machine().lower() in ("x86_64","amd64") else "x86_64-pc-windows-msvc" if sys.platform=="win32" and __import__('platform').machine().lower() in ("amd64","x86_64") else ""}:ap.error("--native target does not match this runner; refusing foreign execution")
    if a.native and a.native7z is None:ap.error("--native requires --native7z for generated archive interoperability coverage")
    file_entries=[];dirs=[]
    try:
        iszip=ext=="zip"
        declared_total=0
        if iszip:
            preflight_zip(archive)
            with zipfile.ZipFile(archive) as z:
                infos=z.infolist()
                if len(infos)>MAX_MEMBERS:raise ValueError("archive exceeds 4096 member limit")
                seen=set();validated=[]
                for i in infos:
                    if i.file_size>MAX_MEMBER:raise ValueError("archive member exceeds 128 MiB limit")
                    declared_total+=i.file_size
                    if declared_total>MAX_TOTAL:raise ValueError("archive exceeds 512 MiB uncompressed limit")
                    name=safe_name(i.filename.rstrip("/"))
                    if name in seen:raise ValueError("duplicate archive paths")
                    seen.add(name)
                    mode=(i.external_attr>>16)&0xffff
                    kind=stat.S_IFMT(mode)
                    if stat.S_ISLNK(mode) or (not i.is_dir() and kind not in (0,stat.S_IFREG)):raise ValueError("archive contains non-regular member")
                    if i.is_dir() and kind not in (0,stat.S_IFDIR):raise ValueError("directory record has inconsistent member type")
                    if i.is_dir(): dirs.append(name)
                    else:
                        if kind not in (0,stat.S_IFREG):raise ValueError("archive contains non-regular member")
                        validated.append((name,i))
                for name,i in validated:
                    with z.open(i) as f:
                        data=f.read(MAX_MEMBER+1)
                        if len(data)!=i.file_size:raise ValueError("archive member size differs from declaration")
                    file_entries.append((name,data))
        else:
            with tarfile.open(archive,"r:gz") as t:
                count=0;validated=[]
                for i in t:
                    count+=1
                    if count>MAX_MEMBERS:raise ValueError("archive exceeds 4096 member limit")
                    name=safe_name(i.name)
                    if i.size<0 or i.size>MAX_MEMBER:raise ValueError("invalid or oversized archive member")
                    if not i.isdir():
                        declared_total+=i.size
                        if declared_total>MAX_TOTAL:raise ValueError("archive exceeds 512 MiB uncompressed limit")
                    if i.isdir():dirs.append(name)
                    elif not i.isfile():raise ValueError(f"non-regular archive member: {name}")
                    else:validated.append((name,i))
                for name,i in validated:
                    f=t.extractfile(i)
                    if f is None:raise ValueError(f"unreadable member: {name}")
                    data=f.read(MAX_MEMBER+1)
                    if len(data)!=i.size:raise ValueError("archive member size differs from declaration")
                    file_entries.append((name,data))
    except (tarfile.TarError,zipfile.BadZipFile,EOFError,ValueError) as e:ap.error(f"invalid archive: {e}")
    names=[n for n,_ in file_entries]+dirs
    if len(names)!=len(set(names)):ap.error("duplicate archive paths")
    expected_dirs={str(PurePosixPath(n).parent) for n in [f"{root}/{x}" for x in REQUIRED|{exe}]}
    for n in expected(root,exe,{"packages":[],"runtime_components":[]}): expected_dirs.update(str(PurePosixPath(parent)) for parent in list(PurePosixPath(n).parents)[:-1] if str(parent)!=".")
    if any(d not in expected_dirs or d in {n for n,_ in file_entries} for d in dirs):ap.error("unexpected or conflicting directory member")
    index=dict(file_entries)
    if len(index)!=len(file_entries):ap.error("duplicate regular file paths")
    try:inventory=json.loads(index[f"{root}/THIRD-PARTY.json"])
    except (KeyError,json.JSONDecodeError):ap.error("missing or invalid THIRD-PARTY.json")
    if not isinstance(inventory,dict) or not isinstance(inventory.get("project"),dict):ap.error("invalid source inventory structure")
    if inventory["project"]!={"name":"bytepleat","version":a.version}:ap.error("source inventory identity/version mismatch")
    try:target_inventory=json.loads(index[f"{root}/THIRD-PARTY-{a.target}.json"])
    except (KeyError,json.JSONDecodeError):ap.error("missing or invalid target dependency inventory")
    if not isinstance(target_inventory,dict) or target_inventory.get("target")!=a.target or target_inventory.get("project")!={"name":"bytepleat","version":a.version} or target_inventory.get("unresolved_gaps") or any(isinstance(x,dict) and x.get("notice_status")=="unresolved" for x in target_inventory.get("packages",[])):
        ap.error("target dependency inventory identity or notice status invalid")
    if target_inventory.get("cargo_lock_sha256")!=sha_bytes(index[f"{root}/Cargo.lock"]):ap.error("target inventory Cargo.lock SHA-256 mismatch")
    try:build=json.loads(index[f"{root}/BUILD-INFO.json"])
    except (KeyError,json.JSONDecodeError):ap.error("missing or invalid BUILD-INFO.json")
    if build!={"schema_version":1,"project":"bytepleat","version":a.version,"target":a.target,"revision":a.revision,"binary_sha256":sha_bytes(index[f"{root}/{exe}"])}:ap.error("build identity or binary digest mismatch")
    expected_files={f"{root}/{x}" for x in REQUIRED}|{f"{root}/{exe}",f"{root}/THIRD-PARTY-{a.target}.json"}
    for notice in iter_notices(target_inventory):expected_files.add(f"{root}/{safe_name(notice['path'])}")
    if set(index)!=expected_files:ap.error(f"archive member set mismatch (missing={sorted(expected_files-set(index))}, extra={sorted(set(index)-expected_files)})")
    lock=index[f"{root}/Cargo.lock"].decode("utf-8")
    if target_inventory.get("cargo_lock_sha256")!=sha_bytes(index[f"{root}/Cargo.lock"]):ap.error("target inventory Cargo.lock SHA-256 mismatch")
    if not re.search(r'^name = "bytepleat"\nversion = "'+re.escape(a.version)+r'"$',lock,re.M):ap.error("Cargo.lock version mismatch")
    manifest=index[f"{root}/Cargo.toml"].decode("utf-8")
    if not re.search(r'^name\s*=\s*"bytepleat"$',manifest,re.M) or not re.search(r'^version\s*=\s*"'+re.escape(a.version)+r'"$',manifest,re.M):ap.error("Cargo.toml source identity/version mismatch")
    binary=index[f"{root}/{exe}"];binary_hash=sha_bytes(binary)
    # Validate all notice payload bytes against the inventory before writing anything.
    for notice in iter_notices(target_inventory):
        p=safe_name(notice["path"]);data=index[f"{root}/{p}"]
        if sha_bytes(data)!=notice.get("sha256"):ap.error(f"license notice digest mismatch: {p}")
    if a.native:
        with tempfile.TemporaryDirectory(prefix="bytepleat-verified-") as td:
            d=Path(td); exe_path=d/exe;exe_path.write_bytes(binary);exe_path.chmod(0o755)
            p=subprocess.run([str(exe_path),"--version"],capture_output=True,text=True,timeout=15)
            if p.returncode or p.stdout.strip()!=f"bytepleat {a.version}":ap.error("extracted binary version check failed")
            smoke=d/"native-smoke.json";subprocess.run([sys.executable,str(ROOT/"scripts/native_smoke.py"),"--binary",str(exe_path),"--output",str(smoke),"--require-tools"],check=True)
            validation=d/"archive-validation.json";subprocess.run([sys.executable,str(ROOT/"scripts/validate_archives.py"),"--binary",str(exe_path),"--native7z",str(a.native7z.resolve()),"--output",str(validation)],check=True)
    out.parent.mkdir(parents=True,exist_ok=True)
    report={"schema_version":1,"archive":asset,"archive_sha256":digest,"target":a.target,"version":a.version,"revision":a.revision,"members":len(index),"binary_sha256":binary_hash,"native_execution":a.native,"status":"pass"}
    tmp=out.with_suffix(out.suffix+".tmp");tmp.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf8");os.replace(tmp,out);print(json.dumps(report,sort_keys=True));return 0
if __name__=="__main__":
    try:raise SystemExit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as e:print(f"verify_packages: {e}",file=sys.stderr);raise SystemExit(2)
