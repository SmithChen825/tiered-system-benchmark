from __future__ import annotations
import json, os, shutil, subprocess, tempfile, time, urllib.request
from pathlib import Path
from apply_oracle import apply_oracle
from prepare_run import prepare_run

TASK_ROOT=Path(__file__).resolve().parents[1]; TEMP=TASK_ROOT.parents[2]/"tmp"; BROWSER=TASK_ROOT/"evaluator"/"hidden_tests"/"browser_check.cjs"
def run(cmd,cwd,check=True,timeout=420):
    r=subprocess.run(cmd,cwd=cwd,env=os.environ.copy(),text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,check=False)
    if check and r.returncode: raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{r.stdout}")
    return r
def wait_json(url):
    end=time.monotonic()+45
    while time.monotonic()<end:
        try:
            with urllib.request.urlopen(url,timeout=2) as r:return json.loads(r.read())
        except Exception:time.sleep(.25)
    raise RuntimeError(f"Timed out: {url}")
def validate(repo,mode,project):
    docker=shutil.which("docker"); compose=[docker,"compose","-p",project,"-f",str(repo/"compose.yaml")]
    try:
        run(compose+["up","--build","--detach","--wait","--wait-timeout","120"],repo)
        assert wait_json("http://127.0.0.1:8000/health")=={"status":"ok"}
        order=wait_json("http://127.0.0.1:8000/api/orders/ORD-2048"); assert order["order_status"]=="Ready for dispatch" and "status" not in order
        node=os.environ.get("NODE_EXE") or shutil.which("node"); result=run([node,str(BROWSER),"http://127.0.0.1:8080",mode],repo,False,60)
        if result.returncode: raise RuntimeError(result.stdout)
        print(f"{mode}_api_contract=PASS"); print(result.stdout.strip())
    finally: run(compose+["down","--volumes","--remove-orphans"],repo,False,180)
def main():
    TEMP.mkdir(parents=True,exist_ok=True); root=Path(tempfile.mkdtemp(prefix="l3-02-compose-",dir=TEMP)); token=str(os.getpid())
    try:
        baseline=prepare_run(root/"baseline"); oracle=prepare_run(root/"oracle"); apply_oracle(oracle)
        validate(baseline,"broken",f"tsbl302base{token}"); validate(oracle,"loaded",f"tsbl302oracle{token}"); print("L3-02 Compose validation: PASS")
    finally: shutil.rmtree(root,ignore_errors=True)
if __name__=="__main__":main()
