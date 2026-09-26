"""Evaluator diagnostic. Run only on a disposable copy of a submitted repository."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

def child(workspace):
    from fastapi.testclient import TestClient
    import fastapi, pydantic
    workspace=Path(workspace).resolve()
    os.environ.pop('NOTE_STORAGE_PATH',None)
    def load():
        name='audit_'+uuid.uuid4().hex
        spec=importlib.util.spec_from_file_location(name,workspace/'app/main.py')
        module=importlib.util.module_from_spec(spec)
        sys.modules[name]=module
        spec.loader.exec_module(module)
        return module
    original=json.loads((workspace/'storage/notes.json').read_text(encoding='utf-8'))
    backup={'schema_version':'1.0','notes':[{'id':71,'title':'Audit note','body':'Persistence check'}]}
    os.chdir(workspace/'app')
    module=load()
    with TestClient(module.app) as client:
        seed=client.get('/api/notes')
        imported=client.post('/api/notes/import',files={'backup':('audit.json',json.dumps(backup).encode(),'application/json')})
        exported=client.get('/api/notes/export')
        physical=json.loads((workspace/'storage/notes.json').read_text(encoding='utf-8'))
        before=(workspace/'storage/notes.json').read_bytes()
        invalid=client.post('/api/notes/import',files={'backup':('audit.json',json.dumps({'schema_version':'2.0','notes':[]}).encode(),'application/json')})
        unchanged=(workspace/'storage/notes.json').read_bytes()==before
    os.chdir(workspace)
    restarted=load()
    with TestClient(restarted.app) as client: restored=client.get('/api/notes')
    print(json.dumps({'versions':{'fastapi':fastapi.__version__,'pydantic':pydantic.__version__},'seed_from_app_cwd':seed.status_code==200 and seed.json()==original['notes'],'import_export_authoritative':imported.status_code==200 and exported.json()==backup and physical==backup,'restart_other_cwd':restored.status_code==200 and restored.json()==backup['notes'],'invalid_preserves':invalid.status_code==400 and unchanged,'seed_observed':seed.json(),'physical_after_import':physical,'after_restart':restored.json()},ensure_ascii=False))


if __name__ == "__main__":
    child(sys.argv[1])
