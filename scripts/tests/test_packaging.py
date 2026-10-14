"""Security and provenance tests for release packaging using synthetic archives."""
from __future__ import annotations
import hashlib, io, json, os, platform, stat, struct, subprocess, sys, tarfile, tempfile, unittest, warnings, zipfile
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SCRIPTS))
import verify_packages
import package_release

TARGET="x86_64-pc-windows-msvc"; VERSION="0.5.0"; ASSET=f"arqlet-{VERSION}-{TARGET}.zip"; ROOT=ASSET[:-4]
REVISION="a"*40

class PackagingSafetyTests(unittest.TestCase):
    def test_rejects_parent_absolute_backslash_and_dot_paths(self):
        for name in ("../escape", "/absolute", "C:/drive", "a\\..\\escape", "./dot", "a/../b", "a//b"):
            with self.subTest(name=name), self.assertRaises(ValueError): verify_packages.safe_name(name)

    def test_package_refuses_existing_asset_or_sidecar_without_mutation(self):
        for leaf in (ASSET,ASSET+".sha256"):
            with self.subTest(leaf=leaf), tempfile.TemporaryDirectory() as td:
                out=Path(td);existing=out/leaf;existing.write_bytes(b"preserve")
                with self.assertRaises(ValueError):package_release.check_create_only(out,ASSET,ASSET+".sha256")
                self.assertEqual(existing.read_bytes(),b"preserve")
                self.assertEqual(list(out.iterdir()),[existing])

    @unittest.skipIf(sys.platform=="win32","portable executable fixture uses a POSIX shebang")
    def test_package_is_reproducible_and_verifies_end_to_end(self):
        target={("Darwin","arm64"):"aarch64-apple-darwin",("Linux","x86_64"):"x86_64-unknown-linux-gnu"}.get((platform.system(),platform.machine()))
        if target is None:self.skipTest("host is outside package helper native target set")
        with tempfile.TemporaryDirectory() as td:
            temp=Path(td);source=temp/"src";source.mkdir();(source/"third-party-licenses").mkdir()
            (source/"Cargo.toml").write_text('[package]\nname = "arqlet"\nversion = "0.5.0"\n')
            (source/"Cargo.lock").write_text('version = 4\n\n[[package]]\nname = "arqlet"\nversion = "0.5.0"\n')
            for name in ("README.md","RELEASE.md","LICENSE"):(source/name).write_text(name+"\n")
            (source/"THIRD-PARTY.json").write_text(json.dumps({"project":{"name":"arqlet","version":"0.5.0"},"packages":[],"runtime_components":[]})+'\n')
            original_inventory=(source/"THIRD-PARTY.json").read_bytes()
            bomdir=temp/"bom";bomdir.mkdir();(bomdir/"THIRD-PARTY.json").write_text(json.dumps({"project":{"name":"arqlet","version":"0.5.0"},"target":target,"cargo_lock_sha256":hashlib.sha256((source/"Cargo.lock").read_bytes()).hexdigest(),"packages":[],"runtime_components":[],"unresolved_gaps":[]}))
            binary=temp/"arqlet";binary.write_text(f'#!{sys.executable}\nimport sys\nprint("arqlet 0.5.0")\n');binary.chmod(0o755)
            outputs=[]
            for n in ("one","two"):
                out=temp/n
                cmd=[sys.executable,str(SCRIPTS/"package_release.py"),"--binary",str(binary),"--target",target,"--version","0.5.0","--revision",REVISION,"--output-dir",str(out),"--source-root",str(source),"--bom",str(bomdir/"THIRD-PARTY.json")]
                done=subprocess.run(cmd,capture_output=True,text=True)
                self.assertEqual(done.returncode,0,done.stderr);asset=next(out.glob("arqlet-0.5.0-*"+(".zip" if target.endswith("msvc") else ".tar.gz")))
                self.assertEqual((out/(asset.name+".sha256")).read_text().split()[0],hashlib.sha256(asset.read_bytes()).hexdigest())
                outputs.append((asset,target))
            self.assertEqual(outputs[0][0].read_bytes(),outputs[1][0].read_bytes())
            member=f"arqlet-0.5.0-{target}/THIRD-PARTY.json"
            if outputs[0][0].suffix==".zip":
                with zipfile.ZipFile(outputs[0][0]) as z:self.assertEqual(z.read(member),original_inventory)
            else:
                with tarfile.open(outputs[0][0],"r:gz") as t:self.assertEqual(t.extractfile(member).read(),original_inventory)
            verify=subprocess.run([sys.executable,str(SCRIPTS/"verify_packages.py"),"--archive",str(outputs[0][0]),"--target",target,"--version","0.5.0","--revision",REVISION,"--output",str(temp/"verified.json")],capture_output=True,text=True)
            self.assertEqual(verify.returncode,0,verify.stderr)

    def archive(self, folder: Path, mutations=(), duplicate=False):
        notice=b"MIT notice\n"; notice_path="third-party-licenses/demo/LICENSE"
        inventory={"project":{"name":"arqlet","version":VERSION},"target":TARGET,"cargo_lock_sha256":"0"*64,"packages":[{"name":"demo","version":"1","notices":[{"path":notice_path,"sha256":hashlib.sha256(notice).hexdigest()}]}],"runtime_components":[],"unresolved_gaps":[]}
        files={f"{ROOT}/{name}":b"payload" for name in ("README.md","RELEASE.md","LICENSE","Cargo.lock")}
        files[f"{ROOT}/Cargo.toml"]=f'[package]\nname = "arqlet"\nversion = "{VERSION}"\n'.encode()
        files[f"{ROOT}/Cargo.lock"]=f'name = "arqlet"\nversion = "{VERSION}"\n'.encode()
        inventory["cargo_lock_sha256"]=hashlib.sha256(files[f"{ROOT}/Cargo.lock"]).hexdigest()
        files[f"{ROOT}/THIRD-PARTY.json"]=json.dumps(inventory).encode();files[f"{ROOT}/THIRD-PARTY-{TARGET}.json"]=json.dumps(inventory).encode();files[f"{ROOT}/arqlet.exe"]=b"synthetic executable";files[f"{ROOT}/{notice_path}"]=notice
        files[f"{ROOT}/BUILD-INFO.json"]=json.dumps({"schema_version":1,"project":"arqlet","version":VERSION,"target":TARGET,"revision":REVISION,"binary_sha256":hashlib.sha256(files[f"{ROOT}/arqlet.exe"]).hexdigest()}).encode()
        for key,value in mutations: files[key]=value
        path=folder/ASSET
        with zipfile.ZipFile(path,"w",zipfile.ZIP_STORED) as z:
            for name,data in sorted(files.items()): z.writestr(name,data)
            if duplicate: z.writestr(f"{ROOT}/README.md",b"duplicate")
        d=hashlib.sha256(path.read_bytes()).hexdigest();path.with_name(path.name+".sha256").write_text(f"{d}  {path.name}\n",encoding="ascii")
        return path

    def invoke(self, folder, archive, target=TARGET, version=VERSION):
        return subprocess.run([sys.executable,str(SCRIPTS/"verify_packages.py"),"--archive",str(archive),"--target",target,"--version",version,"--revision",REVISION,"--output",str(folder/"report.json")],capture_output=True,text=True)

    def test_accepts_exact_payload_and_writes_report(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);result=self.invoke(folder,self.archive(folder));self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads((folder/"report.json").read_text())["status"],"pass")

    def test_rejects_duplicate_member(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore");result=self.invoke(folder,self.archive(folder,duplicate=True))
            self.assertNotEqual(result.returncode,0);self.assertIn("duplicate",result.stderr.lower())

    def test_rejects_traversal_member(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder)
            with zipfile.ZipFile(archive,"a") as z:z.writestr("../escape",b"bad")
            digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(archive.name+".sha256").write_text(f"{digest}  {archive.name}\n")
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("unsafe",result.stderr.lower())

    def test_rejects_unexpected_member(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder)
            with zipfile.ZipFile(archive,"a") as z:z.writestr(f"{ROOT}/unexpected.txt",b"extra")
            digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(archive.name+".sha256").write_text(f"{digest}  {archive.name}\n")
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("member set mismatch",result.stderr.lower())

    def test_rejects_symlink_member(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder)
            with zipfile.ZipFile(archive,"a") as z:
                info=zipfile.ZipInfo(f"{ROOT}/link");info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,"../../escape")
            digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(archive.name+".sha256").write_text(f"{digest}  {archive.name}\n")
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("non-regular",result.stderr.lower())

    def test_rejects_declared_oversized_zip_member_before_read(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder)
            raw=bytearray(archive.read_bytes());pos=raw.find(b"PK\x01\x02")
            self.assertGreaterEqual(pos,0);struct.pack_into("<I",raw,pos+24,verify_packages.MAX_MEMBER+1);archive.write_bytes(raw)
            digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(archive.name+".sha256").write_text(f"{digest}  {archive.name}\n")
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("128 mib",result.stderr.lower())

    def test_rejects_excessive_member_count(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder)
            with zipfile.ZipFile(archive,"a") as z:
                for i in range(verify_packages.MAX_MEMBERS):z.writestr(f"{ROOT}/extra-{i}",b"")
            digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(archive.name+".sha256").write_text(f"{digest}  {archive.name}\n")
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("4096",result.stderr)

    def test_rejects_declared_cumulative_payload_before_read(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder)
            with zipfile.ZipFile(archive,"a") as z:
                for i in range(5):z.writestr(f"{ROOT}/payload-{i}",b"x")
            raw=bytearray(archive.read_bytes());offset=0;changed=0
            while True:
                pos=raw.find(b"PK\x01\x02",offset)
                if pos<0:break
                name_len=struct.unpack_from("<H",raw,pos+28)[0];name=bytes(raw[pos+46:pos+46+name_len])
                if name.startswith((ROOT+"/payload-").encode()):struct.pack_into("<I",raw,pos+24,verify_packages.MAX_MEMBER);changed+=1
                offset=pos+46+name_len
            self.assertEqual(changed,5);archive.write_bytes(raw)
            digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(archive.name+".sha256").write_text(f"{digest}  {archive.name}\n")
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("512 mib",result.stderr.lower())

    def test_rejects_windows_invalid_component_and_directory_alias(self):
        for name in (f"{ROOT}/dir/a:b",f"{ROOT}/bad./file",f"{ROOT}/x?y"):
            with self.subTest(name=name),self.assertRaises(ValueError):verify_packages.safe_name(name)
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder)
            with zipfile.ZipFile(archive,"a") as z:z.writestr(f"{ROOT}/README.md/",b"")
            digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(archive.name+".sha256").write_text(f"{digest}  {archive.name}\n")
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0)

    def test_rejects_malicious_tar_member(self):
        target="x86_64-unknown-linux-gnu";asset=f"arqlet-{VERSION}-{target}.tar.gz"
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=folder/asset
            with tarfile.open(archive,"w:gz") as t:
                info=tarfile.TarInfo("../escape");payload=b"generated unsafe path fixture";info.size=len(payload)
                t.addfile(info,io.BytesIO(payload))
            digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(asset+".sha256").write_text(f"{digest}  {asset}\n")
            result=self.invoke(folder,archive,target=target);self.assertNotEqual(result.returncode,0);self.assertIn("unsafe",result.stderr.lower())

    def test_rejects_missing_notice_and_modified_notice(self):
        for mutation in ("missing","changed"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                folder=Path(td);archive=self.archive(folder)
                if mutation=="missing":
                    with zipfile.ZipFile(archive) as z: files={n:z.read(n) for n in z.namelist() if not n.endswith("/LICENSE")}
                    archive.unlink()
                    with zipfile.ZipFile(archive,"w") as z:
                        for n,b in files.items():z.writestr(n,b)
                else:
                    with zipfile.ZipFile(archive,"a") as z:z.writestr(f"{ROOT}/third-party-licenses/demo/LICENSE",b"tampered")
                digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(archive.name+".sha256").write_text(f"{digest}  {archive.name}\n")
                result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0)

    def test_rejects_lock_version_and_inventory_identity_mismatch(self):
        for mutation in ((f"{ROOT}/Cargo.lock",b'name = "arqlet"\nversion = "0.4.0"\n'),):
            with tempfile.TemporaryDirectory() as td:
                folder=Path(td);archive=self.archive(folder,[mutation]);result=self.invoke(folder,archive)
                self.assertNotEqual(result.returncode,0);self.assertIn("Cargo.lock",result.stderr)

    def test_rejects_inventory_project_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder)
            with zipfile.ZipFile(archive) as z: files={n:z.read(n) for n in z.namelist()}
            inventory=json.loads(files[f"{ROOT}/THIRD-PARTY.json"]);inventory["project"]["name"]="mosaic-byte";files[f"{ROOT}/THIRD-PARTY.json"]=json.dumps(inventory).encode()
            archive.unlink()
            with zipfile.ZipFile(archive,"w") as z:
                for name,data in files.items():z.writestr(name,data)
            digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_name(archive.name+".sha256").write_text(f"{digest}  {archive.name}\n")
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("inventory identity",result.stderr.lower())

    def test_rejects_build_revision_or_binary_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder,[(f"{ROOT}/BUILD-INFO.json",json.dumps({"schema_version":1,"project":"arqlet","version":VERSION,"target":TARGET,"revision":"b"*40,"binary_sha256":hashlib.sha256(b"synthetic executable").hexdigest()}).encode())])
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("build identity",result.stderr.lower())

    def test_rejects_manifest_source_version_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder,[(f"{ROOT}/Cargo.toml",b'[package]\nname = "arqlet"\nversion = "0.4.0"\n')])
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("Cargo.toml",result.stderr)

    def test_rejects_invalid_sidecar_before_archive_processing(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);archive=self.archive(folder);archive.with_name(archive.name+".sha256").write_text("0"*64+"  "+archive.name+"\n")
            result=self.invoke(folder,archive);self.assertNotEqual(result.returncode,0);self.assertIn("sha-256",result.stderr.lower())

if __name__=="__main__":unittest.main()
