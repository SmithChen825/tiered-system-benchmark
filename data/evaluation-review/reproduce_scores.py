"""Reproduce reviewed scores from exported original checks and diagnostic evidence.

No model calls, network, Docker, or changes to submitted repositories.
Run from any directory: python path/to/reproduce_scores.py
"""
import copy
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent

def read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))

def counts(checks):
    assert checks and all(isinstance(v, bool) for v in checks.values())
    return {"passed": sum(checks.values()), "applicable": len(checks)}

def main():
    original = read("original_scores.json")["rows"]
    evidence = read("diagnostic_evidence.json")
    assert len(original) == len({r["run_id"] for r in original}) == 144
    assert len({(r["task"], r["system"], r["repetition"]) for r in original}) == 144
    assert set(Counter(r["task"] for r in original).values()) == {12}
    indexed = {}
    for task, entries in evidence.items():
        expected_ids = {r["run_id"] for r in original if r["task"] == task}
        assert len(entries) == 12 and {r["run_id"] for r in entries} == expected_ids
        indexed[task] = {r["run_id"]: r for r in entries}
    output = []
    for row in original:
        func, arch = copy.deepcopy(row["functional"]), copy.deepcopy(row["architecture"])
        assert row["success"] == (row["stopping_reason"] == "submitted" and all(func.values()) and all(arch.values()))
        task, run_id = row["task"], row["run_id"]
        if task == "L2-03":
            d = indexed[task][run_id]
            assert d["returncode"] == 0
            func["seed_notes"] = d["seed_from_app_cwd"]
            func["import_export"] = d["import_export_authoritative"]
            func["restart_persistence"] = d["restart_other_cwd"]
            arch["authoritative_project_store"] = d["seed_from_app_cwd"] and d["import_export_authoritative"]
            arch["valid_import_persists"] = d["restart_other_cwd"] and d["import_export_authoritative"]
        elif task == "L3-01":
            d = indexed[task][run_id]
            assert d["returncode"] == 0
            arch["wildcard_policy_rejected"] = d["finite_policy_within_public_boundary"]
            # Historical ID retained for joining; rejection of 5173 is no longer required.
            arch["stale_and_unrelated_origins_rejected"] = d["unrelated_origins_rejected"] and d["finite_policy_within_public_boundary"]
        elif task == "L4-02":
            d = indexed[task][run_id]
            cases = d["cases"]
            assert len(cases) == 10 and cases[0]["case"] == "omitted"
            arch["validated_active_default"] = cases[0]["passed"] and d["initial_records_preserved"]
            arch["status_domain_preserved"] = all(c["passed"] for c in cases[1:])
        success = row["stopping_reason"] == "submitted" and all(func.values()) and all(arch.values())
        output.append({"run_id": run_id, "task": task, "system": row["system"], "stopping_reason": row["stopping_reason"], "original_success": row["success"], "reviewed_success": success, "original_functional": counts(row["functional"]), "original_architecture": counts(row["architecture"]), "functional": counts(func), "architecture": counts(arch)})
    assert output == read("reviewed_scores.json")["rows"], "Published reviewed scores differ from reproduction"
    print("Verified all 144 paired rows; original success rule and uniform task coverage pass.")
    for task in sorted({r["task"] for r in output}):
        group = [r for r in output if r["task"] == task]
        print(f"{task}: {sum(r['original_success'] for r in group)}/12 -> {sum(r['reviewed_success'] for r in group)}/12")

if __name__ == "__main__":
    main()
