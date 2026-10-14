#!/usr/bin/env python3
"""Create a deterministic, create-only Bytepleat release archive."""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, platform, re, shutil, stat, subprocess, sys, tarfile, tempfile, zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"aarch64-apple-darwin": ("tar.gz", "bytepleat"), "x86_64-unknown-linux-gnu": ("tar.gz", "bytepleat"), "x86_64-pc-windows-msvc": ("zip", "bytepleat.exe")}
SOURCE_REQUIRED = ("Cargo.toml", "README.md", "RELEASE.md", "LICENSE", "Cargo.lock")

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest()

def fail(message: str) -> None: raise ValueError(message)

def check_create_only(out: Path, asset: str, checksum: str) -> None:
    if out.exists() and not out.is_dir(): fail("output directory is not a directory")
    if (out / asset).exists() or (out / checksum).exists(): fail("refusing to overwrite an existing output")

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", required=True, type=Path); ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    ap.add_argument("--version", required=True); ap.add_argument("--revision", required=True); ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--source-root", type=Path, default=ROOT); ap.add_argument("--bom", type=Path, help="Target-specific inventory from collect_notices.py")
    a = ap.parse_args(); root = a.source_root.resolve(); binary = a.binary.resolve(); out = a.output_dir.resolve()
    if not re.fullmatch(r"\d+\.\d+\.\d+", a.version): ap.error("version must be numeric semver")
    if not re.fullmatch(r"[0-9a-f]{40,64}", a.revision): ap.error("revision must be a full lowercase git object id")
    if a.target not in TARGETS: ap.error("unsupported release target")
    native_target = {("Darwin","arm64"):"aarch64-apple-darwin",("Linux","x86_64"):"x86_64-unknown-linux-gnu",("Windows","AMD64"):"x86_64-pc-windows-msvc",("Windows","x86_64"):"x86_64-pc-windows-msvc"}.get((platform.system(),platform.machine()))
    if native_target != a.target: ap.error(f"refusing non-native package creation: runner is {platform.system()} {platform.machine()}, requested {a.target}")
    manifest = (root / "Cargo.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', manifest, re.M)
    if not m or m.group(1) != a.version: ap.error("requested version does not match Cargo.toml")
    if not re.search(r'^name\s*=\s*"bytepleat"$', manifest, re.M): ap.error("Cargo.toml package identity is not bytepleat")
    if not binary.is_file() or binary.is_symlink(): ap.error("binary must be a regular file")
    try: identity = subprocess.run([str(binary), "--version"], check=True, capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e: ap.error(f"cannot query release binary identity: {e}")
    if identity != f"bytepleat {a.version}": ap.error(f"binary identity mismatch: expected 'bytepleat {a.version}', got {identity!r}")
    if not (root / "third-party-licenses").is_dir(): ap.error("missing third-party-licenses")
    for name in SOURCE_REQUIRED + ("THIRD-PARTY.json",):
        if not (root / name).is_file(): ap.error(f"missing required source file: {name}")
    bom = (a.bom or root / "THIRD-PARTY.json").resolve()
    if not bom.is_file(): ap.error("target inventory does not exist")
    try:
        inv = json.loads(bom.read_text(encoding="utf-8"))
        if not isinstance(inv,dict) or not isinstance(inv.get("project"),dict): ap.error("invalid target inventory structure")
        if inv.get("project") != {"name":"bytepleat","version":a.version}: ap.error("inventory project identity/version mismatch")
        if inv.get("target") != a.target: ap.error("inventory target mismatch")
        if inv.get("unresolved_gaps"): ap.error("inventory contains unresolved bundled dependency notice gaps")
        if any(isinstance(x,dict) and x.get("notice_status")=="unresolved" for x in inv.get("packages",[])): ap.error("inventory contains unresolved bundled dependency notices")
        if not re.fullmatch(r"[0-9a-f]{64}",str(inv.get("cargo_lock_sha256",""))) or inv["cargo_lock_sha256"]!=sha(root/"Cargo.lock"): ap.error("inventory Cargo.lock SHA-256 mismatch")
    except (ValueError, json.JSONDecodeError) as e: ap.error(f"invalid target inventory: {e}")
    notice_paths={}
    for group in ("packages","runtime_components"):
        if not isinstance(inv.get(group,[]),list): ap.error(f"inventory {group} must be an array")
    for item in inv.get("packages",[])+inv.get("runtime_components",[]):
        if not isinstance(item,dict): ap.error("invalid target inventory component")
        for field in ("notices","vendored_component_notices"):
            if not isinstance(item.get(field,[]),list): ap.error(f"inventory {field} must be an array")
        for notice in item.get("notices",[])+item.get("vendored_component_notices",[]):
            if not isinstance(notice,dict) or not isinstance(notice.get("path"),str) or not isinstance(notice.get("sha256"),str) or not re.fullmatch(r"[0-9a-f]{64}",notice["sha256"]): ap.error("invalid inventory notice record")
            rel=notice.get("path","");pp=PurePosixPath(rel)
            if "\\" in rel or pp.is_absolute() or not pp.parts or pp.parts[0]!="third-party-licenses" or any(x in ("", ".", "..") or ":" in x or x.rstrip(" .")!=x or any(c in x for c in '<>\"|?*') for x in rel.split("/")): ap.error(f"unsafe notice path in inventory: {rel!r}")
            src=bom.parent.joinpath(*pp.parts)
            if not src.is_file() or src.is_symlink() or sha(src)!=notice.get("sha256"): ap.error(f"notice source missing or hash mismatch: {rel}")
            notice_paths[pp.as_posix()]=src
    ext, exe = TARGETS[a.target]; asset = f"bytepleat-{a.version}-{a.target}.{ext}"
    checksum = asset + ".sha256"
    # Check every output before creating the output directory or any staging path.
    try: check_create_only(out,asset,checksum)
    except ValueError as e: ap.error(str(e))
    out.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".bytepleat-package-", dir=out))
    try:
        top = f"bytepleat-{a.version}-{a.target}"; stage = staging / top; stage.mkdir()
        shutil.copyfile(binary, stage / exe); (stage / exe).chmod((stage / exe).stat().st_mode | stat.S_IXUSR)
        for name in SOURCE_REQUIRED + ("THIRD-PARTY.json",): shutil.copyfile(root / name, stage / name)
        shutil.copyfile(bom,stage/f"THIRD-PARTY-{a.target}.json")
        (stage / "BUILD-INFO.json").write_text(json.dumps({"schema_version":1,"project":"bytepleat","version":a.version,"target":a.target,"revision":a.revision,"binary_sha256":sha(binary)},sort_keys=True,indent=2)+"\n",encoding="utf-8")
        for rel,src in sorted(notice_paths.items()):
            dest=stage/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        members = sorted((p for p in stage.rglob("*") if p.is_file()), key=lambda p: p.relative_to(staging).as_posix())
        if ext == "zip":
            with zipfile.ZipFile(staging / asset, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                for p in members:
                    info = zipfile.ZipInfo(p.relative_to(staging).as_posix(), (2020,1,1,0,0,0)); info.create_system=3; info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=(0o100755 if p.name==exe else 0o100644) << 16
                    z.writestr(info, p.read_bytes())
        else:
            with (staging / asset).open("wb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
                    with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tf:
                        for p in members:
                            ti=tf.gettarinfo(str(p), arcname=p.relative_to(staging).as_posix()); ti.uid=ti.gid=0; ti.uname=ti.gname=""; ti.mtime=0; ti.mode=0o755 if p.name==exe else 0o644
                            with p.open("rb") as f: tf.addfile(ti, f)
        digest = sha(staging / asset)
        tmp = staging / checksum
        with tmp.open("w",encoding="ascii",newline="\n") as f:f.write(f"{digest}  {asset}\n")
        # Publish both create-only files only after successful staging.
        published=[]
        os.link(staging / asset, out / asset); published.append(out / asset)
        os.link(tmp, out / checksum); published.append(out / checksum)
    except Exception:
        for p in locals().get("published",[]):
            try: p.unlink()
            except FileNotFoundError: pass
        raise
    finally: shutil.rmtree(staging, ignore_errors=True)
    print(json.dumps({"asset":asset,"sha256":digest,"target":a.target,"version":a.version,"revision":a.revision}, sort_keys=True)); return 0
if __name__ == "__main__":
    try: raise SystemExit(main())
    except (ValueError, OSError) as e: print(f"package_release: {e}", file=sys.stderr); raise SystemExit(2)
