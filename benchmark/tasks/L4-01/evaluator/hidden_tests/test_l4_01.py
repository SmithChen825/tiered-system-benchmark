import ast
import os
from pathlib import Path


REPOSITORY = Path(os.environ["L4_01_REPO"]).resolve()


def class_annotations(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
            }
    raise AssertionError(f"Class {class_name} not found in {path}")


def test_orm_user_model_has_no_age_mapping():
    fields = class_annotations(REPOSITORY / "backend" / "app" / "models.py", "User")
    assert fields == {"id", "name", "email", "role"}


def test_api_user_schema_has_no_age_field():
    fields = class_annotations(
        REPOSITORY / "backend" / "app" / "schemas.py", "UserRead"
    )
    assert fields == {"id", "name", "email", "role"}


def test_vue_table_has_no_age_reference():
    component = (REPOSITORY / "frontend" / "src" / "App.vue").read_text(
        encoding="utf-8"
    )
    assert "user.age" not in component
    assert "<th>Age</th>" not in component
    assert "default age" not in component.lower()


def test_database_initial_state_keeps_age_absent():
    initialization = (REPOSITORY / "database" / "init.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "create table users" in initialization
    assert " age " not in initialization
    assert "add column age" not in initialization
    assert "insert into users (name, email, role)" in initialization


def test_frontend_backend_and_database_remain_separate_services():
    compose = (REPOSITORY / "compose.yaml").read_text(encoding="utf-8")
    assert "  db:" in compose
    assert "  backend:" in compose
    assert "  frontend:" in compose
    assert "postgres:16.6-alpine@sha256:" in compose


def test_api_contract_uses_remaining_fields():
    main_source = (REPOSITORY / "backend" / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    assert '"/api/users"' in main_source
    assert "select(User).order_by(User.id)" in main_source
    assert "http://127.0.0.1:8080" in main_source
