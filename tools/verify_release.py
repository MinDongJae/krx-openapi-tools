"""Offline release checks, suitable for the registered iMac runner."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
out = root / '_mac_out'
out.mkdir(exist_ok=True)
suite = unittest.defaultTestLoader.discover(str(root/'tests'))
with (out/'tests.txt').open('w', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
receipt = {'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'authenticated_live_calls':False}
if result.wasSuccessful():
    with tempfile.TemporaryDirectory() as temp:
        wheel_dir = Path(temp)/'wheel'
        build_source = Path(temp)/'source'
        shutil.copytree(root, build_source, ignore=shutil.ignore_patterns('.git','_mac_out','__pycache__','*.egg-info','build','dist'))
        subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--no-build-isolation','--wheel-dir',str(wheel_dir),str(build_source)],check=True,stdout=(out/'wheel-build.txt').open('w',encoding='utf-8'),stderr=subprocess.STDOUT)
        wheel = next(wheel_dir.glob('*.whl'))
        target = Path(temp)/'installed'
        subprocess.run([sys.executable,'-m','pip','install','--no-deps','--target',str(target),str(wheel)],check=True,stdout=subprocess.DEVNULL)
        code="import sys;sys.path.insert(0,sys.argv[1]);from krx_openapi_tools import contract;assert len(contract('kospi')['fields'])==15;print('installed wheel resource verified')"
        subprocess.run([sys.executable,'-I','-c',code,str(target)],cwd=temp,check=True,stdout=(out/'wheel-import.txt').open('w',encoding='utf-8'))
        receipt['wheel_resource_verified']=True
        (out/wheel.name).write_bytes(wheel.read_bytes())
(out/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
raise SystemExit(0 if result.wasSuccessful() and receipt.get('wheel_resource_verified') else 1)
