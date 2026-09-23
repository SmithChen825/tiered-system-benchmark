# L1-01 Missing Product Images

This researcher-facing package implements the representative Level 1 pilot task. The evaluated system receives only a fresh copy of `fixture_repo/` and the frozen `public_task_brief.md`.

Package separation:

- `fixture_repo/`: faulty Nginx-served static website visible to the agent;
- `public_task_brief.md`: complete task brief with no intentional information gap;
- `evaluator/hidden_tests/`: evaluator-only filesystem and browser checks;
- `oracle/`: known-good repair outside the agent workspace;
- `scripts/`: fresh-run preparation, oracle application, and reset-cycle validation.

## Fault model

The product image files exist beneath `site/assets/products/`, but the three product cards still request a retired `/legacy-assets/products/` directory. CSS and page content remain valid, isolating the task to stale asset references.

## Local validation

Python checks require the pinned `pytest` version in `requirements.txt`. The browser check requires Node.js, Playwright 1.62.0, and a Chromium-compatible browser. Set `NODE_EXE`, `NODE_PATH`, and (when Playwright's bundled browser is unavailable) `BROWSER_EXE` if these are not globally discoverable, then run:

```powershell
python scripts/validate_cycle.py
```

The validator proves:

```text
fresh reset -> intended filesystem/browser failures
             -> oracle repair -> all checks pass
             -> fresh reset -> same failures
```

The Nginx base is pinned by both tag and multi-platform content digest: `nginx:1.27.3-alpine@sha256:814a8e88df978ade80e584cc5b333144b9372a8e3c98872d07137dbf3b44d0e4`.
