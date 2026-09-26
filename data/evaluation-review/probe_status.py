"""L4-02 semantic status checks, run only in evaluator-owned containers."""
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request

INVALID = [None, "pending", "", 0, True, [], {}]


def schema_checks(path):
    import pydantic
    assert pydantic.__version__ == "2.10.4", pydantic.__version__
    spec = importlib.util.spec_from_file_location("submitted_schemas", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = []
    for label, extra in [("omitted", {})] + [(repr(v), {"status": v}) for v in ["active", "inactive", *INVALID]]:
        try:
            obj = module.CustomerCreate(name="Probe", email="probe@example.test", **extra)
            cases.append(dict(case=label, accepted=True, status=getattr(obj, "status", None)))
        except pydantic.ValidationError:
            cases.append(dict(case=label, accepted=False))
    default = cases[0]["accepted"] and cases[0].get("status") == "active"
    domain = all(c["accepted"] and c.get("status") == v for c, v in zip(cases[1:3], ["active", "inactive"])) and all(not c["accepted"] for c in cases[3:])
    return dict(pydantic=pydantic.__version__, cases=cases, request_default=default, request_domain=domain)


def runtime_checks():
    import psycopg
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    def rows():
        with psycopg.connect(url) as conn:
            return conn.execute("SELECT id,name,email,status FROM customers ORDER BY id").fetchall()
    def request(method, payload=None):
        req = urllib.request.Request("http://127.0.0.1:8000/api/customers", data=None if payload is None else json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode(errors="replace")
    original = rows()
    cases = []
    for i, (label, extra, expected) in enumerate([("omitted", {}, "active"), ("active", {"status": "active"}, "active"), ("inactive", {"status": "inactive"}, "inactive")] + [(repr(v), {"status": v}, None) for v in INVALID]):
        email = f"semantic-{i}@example.test"
        before = rows()
        code, body = request("POST", dict(name="Semantic probe", email=email, **extra))
        after = rows()
        if expected is None:
            passed = 400 <= code < 500 and before == after
        else:
            read_code, read_body = request("GET")
            matching = [r for r in after if r[2] == email]
            passed = code == 201 and isinstance(body, dict) and body.get("status") == expected and len(matching) == 1 and matching[0][3] == expected and read_code == 200 and isinstance(read_body, list) and any(r.get("email") == email and r.get("status") == expected for r in read_body)
        cases.append(dict(case=label, http_status=code, response=body, passed=passed, database_before=before, database_after=after))
    final = rows()
    retained = all(row in final for row in original)
    return dict(cases=cases, initial_records_preserved=retained, persistence_mapping=retained and all(c["passed"] for c in cases[:3]), api_status_domain=all(c["passed"] for c in cases[1:]))


if __name__ == "__main__":
    result = schema_checks(sys.argv[2]) if sys.argv[1] == "schema" else runtime_checks()
    print(json.dumps(result, ensure_ascii=False))
