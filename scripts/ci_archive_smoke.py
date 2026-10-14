#!/usr/bin/env python3
"""Locate an installed 7-Zip and invoke the portable archive interop suite."""
import argparse, os, shutil, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser(description='Run Bytepleat interoperability checks with native 7-Zip');p.add_argument('--binary',required=True);p.add_argument('--output',required=True);p.add_argument('--native7z');a=p.parse_args()
native=a.native7z or shutil.which('7zz') or shutil.which('7z')
if not native and sys.platform=='win32':
 for key in ('ProgramFiles','ProgramFiles(x86)'):
  path=Path(os.environ.get(key,''))/'7-Zip/7z.exe'
  if path.is_file():native=str(path);break
if not native:raise SystemExit('Native 7-Zip is required for archive interoperability checks')
raise SystemExit(subprocess.call([sys.executable,str(Path(__file__).with_name('validate_archives.py')),'--binary',a.binary,'--native7z',native,'--output',a.output]))
