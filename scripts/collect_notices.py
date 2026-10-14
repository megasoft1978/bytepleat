#!/usr/bin/env python3
"""Build a target-specific dependency notice inventory from locked Cargo metadata."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, sys
from pathlib import Path
from typing import Optional

ROOT=Path(__file__).resolve().parents[1]
def digest(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def release_reachable(nodes:dict,root_id:str)->set[str]:
    reached=set();todo=[root_id]
    while todo:
        pid=todo.pop()
        if pid in reached:continue
        reached.add(pid);node=nodes.get(pid)
        if node:
            for dep in node.get("deps",[]):
                kinds=dep.get("dep_kinds",[])
                if kinds and not any(k.get("kind") in (None,"build") for k in kinds):continue
                todo.append(dep["pkg"])
    return reached
def rust_commit_hash(version:str)->Optional[str]:
    return next((line.split(":",1)[1].strip() for line in version.splitlines() if line.startswith("commit-hash:")),None)
def main()->int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--target",required=True);ap.add_argument("--output-dir",required=True,type=Path);ap.add_argument("--source-root",type=Path,default=ROOT);a=ap.parse_args()
    root=a.source_root.resolve();out=a.output_dir.resolve()
    if out.exists() and any(out.iterdir()):ap.error("output directory must be absent or empty")
    old=json.loads((root/"THIRD-PARTY.json").read_text(encoding="utf-8"))
    p=subprocess.run(["cargo","metadata","--locked","--format-version","1","--filter-platform",a.target],cwd=root,capture_output=True,text=True)
    if p.returncode:ap.error("cargo metadata failed: "+p.stderr[-3000:])
    meta=json.loads(p.stdout);packages={x["id"]:x for x in meta["packages"]};nodes={x["id"]:x for x in meta["resolve"]["nodes"]}
    roots=[x["id"] for x in meta["packages"] if x.get("name")=="arqlet"]
    # Select the package manifest at this checkout root, not an unrelated workspace package.
    roots=[pid for pid in roots if Path(packages[pid]["manifest_path"]).resolve()==(root/"Cargo.toml").resolve()]
    if len(roots)!=1:ap.error("could not identify unique arqlet package in Cargo metadata")
    reached=release_reachable(nodes,roots[0])
    oldpkgs={(x["name"],x["version"]):x for x in old.get("packages",[])};result=[];missing=[]
    for pid in sorted(reached):
        pck=packages[pid]
        if pid==roots[0]:continue
        record=oldpkgs.get((pck["name"],pck["version"]))
        if record is None:
            missing.append({"package":pck["name"],"version":pck["version"],"reason":"No previously reviewed notice record; declared metadata is retained without inferring or fabricating license text."})
            result.append({"name":pck["name"],"version":pck["version"],"cargo_source":pck.get("source"),"declared_license":pck.get("license"),"repository":pck.get("repository"),"notices":[],"vendored_component_notices":[],"notice_status":"unresolved"});continue
        copied=[]
        for notice in record.get("notices",[])+record.get("vendored_component_notices",[]):
            src=root/notice["path"]
            if not src.is_file() or digest(src)!=notice.get("sha256"):ap.error(f"notice source missing or changed: {notice['path']}")
            rel=Path(notice["path"]);dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);copied.append(notice)
        result.append({**record,"notices":record.get("notices",[]),"vendored_component_notices":record.get("vendored_component_notices",[])})
    runtime=[]
    rustc=subprocess.run(["rustc","--version","--verbose"],cwd=root,capture_output=True,text=True,check=True)
    sysroot=Path(subprocess.run(["rustc","--print","sysroot"],cwd=root,capture_output=True,text=True,check=True).stdout.strip())
    licenses=sysroot/"share/doc/rust/licenses"
    rust_commit=rust_commit_hash(rustc.stdout)
    if licenses.is_dir():
        license_files=[];visited=0
        for current,dirs,files in __import__("os").walk(licenses,followlinks=False):
            dirs[:]=sorted(d for d in dirs if not (Path(current)/d).is_symlink())
            for name in sorted(files):
                visited+=1
                if visited>4096:ap.error("Rust sysroot license tree exceeds bounded 4096-file scan")
                src=Path(current)/name
                if src.is_file() and not src.is_symlink():license_files.append(src)
        for src in sorted(license_files):
            rel=Path("third-party-licenses/runtime")/rustc.stdout.splitlines()[0].replace(" ","-")/src.name
            dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
            runtime.append({"component":"Rust standard library distribution","toolchain":rustc.stdout.splitlines()[0],"toolchain_commit":rust_commit,"target":a.target,"source_url":f"https://github.com/rust-lang/rust/tree/{rust_commit or 'master'}","notices":[{"path":rel.as_posix(),"sha256":digest(dst),"source_relative_path":src.name}]})
    else:
        # Minimal toolchains omit the license directory. Search only the two
        # documented sysroot locations and the matching official source tree.
        docroot=sysroot/"share/doc/rust";found=[];visited=0
        if docroot.is_dir():
            for current,dirs,files in __import__("os").walk(docroot,followlinks=False):
                dirs[:]=sorted(d for d in dirs if not (Path(current)/d).is_symlink())
                for name in sorted(files):
                    visited+=1
                    if visited>4096:ap.error("Rust sysroot documentation exceeds bounded 4096-file scan")
                    src=Path(current)/name
                    if name in {"COPYRIGHT","LICENSE-MIT","LICENSE-APACHE"} and src.is_file() and not src.is_symlink():found.append(src)
        if len(found)<2 and rust_commit:
            import urllib.request
            for filename in ("COPYRIGHT","LICENSE-MIT","LICENSE-APACHE"):
                if len(found)>=3: break
                url=f"https://raw.githubusercontent.com/rust-lang/rust/{rust_commit}/"+filename
                try:
                    with urllib.request.urlopen(url,timeout=10) as response: data=response.read(2*1024*1024+1)
                    if len(data)<=2*1024*1024:
                        rel=Path("third-party-licenses/runtime")/rustc.stdout.splitlines()[0].replace(" ","-")/filename
                        dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
                        runtime.append({"component":"Rust standard library distribution","toolchain":rustc.stdout.splitlines()[0],"toolchain_commit":rust_commit,"target":a.target,"source_url":url,"notices":[{"path":rel.as_posix(),"sha256":digest(dst),"source_relative_path":filename}]})
                except (OSError,ValueError): pass
        for src in found:
            rel=Path("third-party-licenses/runtime")/rustc.stdout.splitlines()[0].replace(" ","-")/src.name
            dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
            runtime.append({"component":"Rust standard library distribution","toolchain":rustc.stdout.splitlines()[0],"toolchain_commit":rust_commit,"target":a.target,"source_url":f"https://github.com/rust-lang/rust/tree/{rust_commit or 'master'}","notices":[{"path":rel.as_posix(),"sha256":digest(dst),"source_relative_path":src.name}]})
        if len(found)<2 and not runtime: missing.append({"component":"Rust standard library","reason":"No applicable Rust license texts found in bounded sysroot paths or official matching commit source; no notices fabricated."})
    out.mkdir(parents=True,exist_ok=True)
    systems={"aarch64-apple-darwin":"Apple macOS system libraries are provided by the operating system and are not bundled.","x86_64-unknown-linux-gnu":"GNU/Linux system libraries, including the GNU C library, are provided by the operating system and are not bundled.","x86_64-pc-windows-msvc":"Windows system libraries and the Universal C Runtime are provided by Windows and are not bundled."}
    report={"schema_version":1,"generated_by":"scripts/collect_notices.py","project":{"name":"arqlet","version":packages[roots[0]]["version"]},"target":a.target,"cargo_metadata_filter_platform":a.target,"cargo_lock_sha256":digest(root/"Cargo.lock"),"packages":result,"runtime_components":runtime,"system_libraries":{"status":"not bundled","description":systems.get(a.target,"Target OS system libraries are not bundled.")},"unresolved_gaps":missing,"legal_clearance":"Literal license provenance inventory; no formal legal review performed."}
    (out/"THIRD-PARTY.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"target":a.target,"packages":len(result),"unresolved_gaps":len(missing)},sort_keys=True));return 0
if __name__=="__main__":
    try:raise SystemExit(main())
    except (OSError,ValueError,subprocess.SubprocessError) as e:print(f"collect_notices: {e}",file=sys.stderr);raise SystemExit(2)
