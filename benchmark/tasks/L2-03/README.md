# L2-03 Saved Notes Import/Export

Deterministic Level 2 task: the FastAPI app resolves its notes file relative to the process working directory instead of the project root. The oracle changes only the default storage-path resolution in `app/main.py`. Validate locally with `python scripts/validate_cycle.py`; run the separate Docker restart validation before freezing the package.

