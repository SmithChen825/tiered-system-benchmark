"""Evaluator diagnostic. Run only on a disposable copy of a submitted repository."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

def child(workspace):
    from fastapi.testclient import TestClient
    from starlette.middleware.cors import CORSMiddleware
    spec=importlib.util.spec_from_file_location('audit_submission',Path(workspace)/'backend/app/main.py')
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    app=m.create_app()
    policies=[x.kwargs for x in app.user_middleware if x.cls is CORSMiddleware]
    permitted={'http://127.0.0.1:8080','http://127.0.0.1:5173'}
    finite_policy=bool(policies) and all(set(x.get('allow_origins',[]))<=permitted and not x.get('allow_origin_regex') for x in policies)
    cases=[]
    origins=['http://127.0.0.1:8080','http://127.0.0.1:5173','https://unrelated.example','http://localhost:5173','http://127.0.0.1:9999','null']
    with TestClient(app) as client:
        for origin in origins:
            response=client.get('/api/account',headers={'Origin':origin})
            preflight=client.options('/api/account',headers={'Origin':origin,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'Content-Type'})
            cases.append({'origin':origin,'get':response.status_code,'acao':response.headers.get('access-control-allow-origin'),'options':preflight.status_code,'options_acao':preflight.headers.get('access-control-allow-origin')})
    required=cases[0]['get']==200 and cases[0]['acao']==origins[0] and cases[0]['options']==200 and cases[0]['options_acao']==origins[0]
    rejected=all(c['acao'] is None and c['options_acao'] is None for c in cases[2:])
    print(json.dumps({'finite_policy_within_public_boundary':finite_policy,'required_origin_works':required,'unrelated_origins_rejected':rejected,'cases':cases}))


if __name__ == "__main__":
    child(sys.argv[1])
