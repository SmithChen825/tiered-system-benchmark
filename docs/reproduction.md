# Local setup and validation

## 1. Requirements

- Python 3.12 and Git for the shared framework and offline tests.
- Task-specific Python packages listed in each task's `requirements.txt`.
- Node.js, the task evaluator's npm dependencies, and Chromium for browser checks.
- Docker with Compose for service-level validation; Level 4 also uses PostgreSQL inside Compose.

Use the exact task dependency files instead of installing unrelated packages. Browser and Compose scripts assume the task's declared service ports are available. Inspect a task's README and scripts before starting its services.

## 2. Check the exported framework

From the repository root:

```sh
python -m benchmark.runner.verify_start_commits --verify
python -m unittest benchmark.runner.tests.test_api_wrapper benchmark.runner.tests.test_api_tools benchmark.runner.tests.test_openai_responses_transport benchmark.runner.tests.test_qwen_vllm_transport
```

These checks are offline and do not make paid provider calls. Temporary verification directories are created under `tmp/`.

## 3. Prepare a disposable example

```sh
python -m benchmark.runner.create_run L3-03 baseline --phase validation
```

This creates `workspaces/validation-L3-03-baseline-r01-a01/repo/` and a separate `runs/validation-L3-03-baseline-r01-a01/` evidence directory. Existing run directories are never overwritten. Preparation alone does not start an agent or launch containers.

## 4. Validate a fault/repair/reset cycle

For an example source/API validation cycle:

```sh
python -m pip install -r benchmark/tasks/L3-03/requirements.txt
python benchmark/tasks/L3-03/scripts/validate_cycle.py
```

The script checks the intended baseline failure, applies the researcher oracle in a disposable copy, verifies the repair, and reproduces the failure after another reset. Full integration coverage additionally requires the task's Compose and Chromium checks; the source/API cycle alone is not the complete end-to-end evaluator.

Task-specific instructions and recorded validation findings are in each task directory. Oracle repairs and hidden tests are researcher material, not agent input.

## 5. Formal execution

This curated export supports offline inspection and validation. It intentionally omits account-specific provider authorizations, live endpoint details, IDE profile directories, and the private operational freeze chain. The original pilot/main execution gates therefore are not ready to run from this clone.

A new deployment requires its own provider configuration, native-version records, execution authorization, and validated freeze manifest. Retained research-specification hashes document their source records; this export is not a replacement for the operational archive.
