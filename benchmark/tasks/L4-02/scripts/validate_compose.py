from __future__ import annotations
import json,os,shutil,subprocess,tempfile,time,urllib.error,urllib.request
from pathlib import Path
from apply_oracle import apply_oracle
from prepare_run import prepare_run

TASK_ROOT=Path(__file__).resolve().parents[1];TEMP=TASK_ROOT.parents[2]/"tmp";BROWSER=TASK_ROOT/"evaluator"/"hidden_tests"/"browser_check.cjs";API="http://127.0.0.1:8000"
def run(cmd,cwd,check=True,timeout=420):
 r=subprocess.run(cmd,cwd=cwd,env=os.environ.copy(),text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,check=False)
 if check and r.returncode:raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{r.stdout}")
 return r
def request(method,path,payload=None):
 data=json.dumps(payload).encode() if payload is not None else None;req=urllib.request.Request(API+path,data=data,method=method,headers={"Content-Type":"application/json","Origin":"http://127.0.0.1:8080"})
 try:
  with urllib.request.urlopen(req,timeout=10) as r:return r.status,json.loads(r.read())
 except urllib.error.HTTPError as e:return e.code,e.read().decode(errors="replace")
def wait_health():
 end=time.monotonic()+60
 while time.monotonic()<end:
  try:
   status,body=request("GET","/health")
   if status==200:return body
  except Exception:pass
  time.sleep(.25)
 raise RuntimeError("backend health timeout")
def scalar(compose,repo,sql):
 return run(compose+["exec","--no-TTY","db","psql","--username","benchmark","--dbname","benchmark","--tuples-only","--no-align","--command",sql],repo,True,60).stdout.strip()
def validate(repo,mode,project):
 docker=shutil.which("docker");compose=[docker,"compose","-p",project,"-f",str(repo/"compose.yaml")]
 try:
  run(compose+["up","--build","--detach","--wait","--wait-timeout","180"],repo)
  assert wait_health()=={"status":"ok"};assert scalar(compose,repo,"SELECT string_agg(column_name,',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='customers';")=="id,name,email,status";assert scalar(compose,repo,"SELECT COUNT(*) FROM customers;")=="2"
  status,body=request("POST","/api/customers",{"name":"Integration Customer","email":"integration@example.test"})
  if mode=="blocked":
   if status<500:raise RuntimeError(f"Baseline unexpectedly created customer: {status} {body}")
  else:
   if status!=201 or body.get("status")!="active":raise RuntimeError(f"Oracle create failed: {status} {body}")
  node=os.environ.get("NODE_EXE") or shutil.which("node");browser=run([node,str(BROWSER),"http://127.0.0.1:8080",mode],repo,False,90)
  if browser.returncode:raise RuntimeError(browser.stdout)
  print(f"{mode}_database_schema=PASS");print(f"{mode}_create_status={status}");print(browser.stdout.strip())
 finally:run(compose+["down","--volumes","--remove-orphans"],repo,False,180)
def main():
 TEMP.mkdir(parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix="l4-02-compose-",dir=TEMP));token=str(os.getpid())
 try:
  baseline=prepare_run(root/"baseline");oracle=prepare_run(root/"oracle");apply_oracle(oracle);validate(baseline,"blocked",f"tsbl402base{token}");validate(oracle,"loaded",f"tsbl402oracle{token}");print("L4-02 Compose validation: PASS")
 finally:shutil.rmtree(root,ignore_errors=True)
if __name__=="__main__":main()
