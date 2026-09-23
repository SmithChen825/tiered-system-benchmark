import ast, os
from pathlib import Path

REPOSITORY = Path(os.environ["L4_02_REPO"]).resolve()

def annotations(path: Path, class_name: str) -> set[str]:
    tree=ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node,ast.ClassDef) and node.name==class_name:
            return {s.target.id for s in node.body if isinstance(s,ast.AnnAssign) and isinstance(s.target,ast.Name)}
    raise AssertionError(f"Missing class {class_name}")

def test_database_schema_contains_required_status_and_seed_values():
    sql=(REPOSITORY/"database"/"init.sql").read_text(encoding="utf-8").lower()
    assert "create table customers" in sql and "status text not null" in sql
    assert "insert into customers (name, email, status)" in sql and sql.count("'active'") >= 2

def test_orm_customer_model_maps_required_status():
    assert annotations(REPOSITORY/"backend"/"app"/"models.py","Customer") == {"id","name","email","status"}

def test_create_schema_supplies_the_frozen_active_default():
    source=(REPOSITORY/"backend"/"app"/"schemas.py").read_text(encoding="utf-8")
    assert annotations(REPOSITORY/"backend"/"app"/"schemas.py","CustomerCreate") == {"name","email","status"}
    assert 'status: Literal["active", "inactive"] = "active"' in source

def test_read_schema_exposes_status():
    assert annotations(REPOSITORY/"backend"/"app"/"schemas.py","CustomerRead") == {"id","name","email","status"}

def test_create_endpoint_persists_the_mapped_status():
    source=(REPOSITORY/"backend"/"app"/"main.py").read_text(encoding="utf-8")
    assert '"/api/customers"' in source and "status_code=201" in source.replace(" ","")
    assert "status=payload.status" in source.replace(" ","")

def test_frontend_reads_status_from_api_without_hard_coding():
    component=(REPOSITORY/"frontend"/"src"/"App.vue").read_text(encoding="utf-8")
    assert "customer.status" in component and ">active<" not in component.lower()

def test_three_service_architecture_and_pinned_database_are_preserved():
    compose=(REPOSITORY/"compose.yaml").read_text(encoding="utf-8")
    assert all(name in compose for name in ("  db:","  backend:","  frontend:"))
    assert "postgres:16.6-alpine@sha256:" in compose
