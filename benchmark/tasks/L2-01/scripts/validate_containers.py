from __future__ import annotations
import json, os, shutil, subprocess, time
from pathlib import Path
from build_images import BASELINE_IMAGE, ORACLE_IMAGE, build_images

TASK_ROOT=Path(__file__).resolve().parents[1]
HTTP=r'''import json,sys,urllib.error,urllib.request
path=sys.argv[1]
try:
 r=urllib.request.urlopen("http://127.0.0.1:8000"+path,timeout=5); status=r.status; body=r.read().decode()
except urllib.error.HTTPError as e: status=e.code; body=e.read().decode()
print(json.dumps({"status":status,"body":body}))'''

def run(command,check=True):
    result=subprocess.run(command,cwd=TASK_ROOT,text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
    if check and result.returncode: raise RuntimeError(f"Command failed: {' '.join(command)}\n{result.stdout}")
    return result

def validate(image,expected,token):
    docker=shutil.which("docker"); name=f"tsb-l2-01-{expected}-{token}"
    try:
        run([docker,"run","--detach","--name",name,image])
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            status=run([docker,"inspect","--format","{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",name],False).stdout.strip()
            if status=="healthy": break
            time.sleep(.5)
        result=json.loads(run([docker,"exec",name,"python","-c",HTTP,"/items/2"]).stdout)
        if result["status"]!=expected: raise RuntimeError(f"Expected {expected}, got {result}")
        if expected==200 and not all(x in result["body"] for x in ("Harbor Pack","Carry","$129.00")): raise RuntimeError(result)
        api=json.loads(run([docker,"exec",name,"python","-c",HTTP,"/api/items/2"]).stdout)
        if api["status"]!=200 or "Harbor Pack" not in api["body"]: raise RuntimeError(api)
        print(f"container_{expected}=PASS")
    finally: run([docker,"rm","--force",name],False)

def main():
    if not shutil.which("docker"): raise RuntimeError("Docker CLI not found")
    build_images(); token=str(os.getpid()); validate(BASELINE_IMAGE,422,token); validate(ORACLE_IMAGE,200,token); print("L2-01 container validation: PASS")
if __name__=="__main__": main()
