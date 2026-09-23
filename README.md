# Tiered System Benchmark (TSB)

**A controlled benchmark for testing how agentic coding systems diagnose and repair faults across frontend, backend, and database layers.**

TSB is the research software for *Benchmarking Agentic Code Generation Tools*, a University of Melbourne thesis by Wenrui Chen, supervised by Prof. Richard Sinnott.

This first release contains the **task suite, evaluation framework, experimental design, and descriptive pilot data**. The 144-run main-experiment results will be added after collection and verification are complete.

## At a glance

| Design | Scope |
|---|---|
| Systems | Cursor, Devin Desktop, GPT-5.4, Qwen2.5-Coder-7B-Instruct |
| Tasks | 12 deterministic debugging tasks across four architectural tiers |
| Main experiment | 12 tasks × 4 systems × 3 fresh repetitions = **144 runs** |
| Pilot | 16 selected runs; 27 retained attempts in the audit index |
| Primary outcome | Normal submission and all required hidden tests and architectural invariants passing |
| Other outcomes | Elapsed time, clarification behaviour, autonomous recovery, and diagnostic test results |

The comparison concerns **complete configured systems**, including their interfaces and execution controls. It is not an isolated ranking of underlying language models.

## Four tiers of debugging

| Tier | Application | What the tasks exercise |
|---|---|---|
| L1 | Static website | Asset paths, responsive navigation, client-side validation |
| L2 | FastAPI application | Routing, requirement clarification, persistent storage |
| L3 | Vue + FastAPI | CORS, response contracts, API endpoint versions |
| L4 | Vue + FastAPI + PostgreSQL | Schema consistency, record creation, database connectivity |

Each task provides a public brief, a faulty starting repository, a deterministic reset, evaluator-only tests, architectural invariants, and a known-good repair. See the [task catalogue](docs/tasks.md).

## Start here

- **Understand the study:** [experimental protocol](docs/protocol.md) and [analysis plan](benchmark/config/analysis_plan.main.json).
- **Inspect a task:** [L3-03 public brief](benchmark/tasks/L3-03/public_task_brief.md), [starting application](benchmark/tasks/L3-03/fixture_repo), and [task package](benchmark/tasks/L3-03).
- **Try the framework:** follow the [local setup and validation guide](docs/reproduction.md).
- **Review the pilot:** read the [pilot summary](docs/pilot.md), [16 selected observations](data/pilot/selected_runs.csv), and [27-attempt index](data/pilot/all_attempts.csv).
- **Understand this release:** read the [release scope](docs/release-scope.md).

## Repository layout

```text
benchmark/
  tasks/       12 task packages: briefs, fixtures, tests, repairs, validation
  runner/      Shared run loop, native recorder, evaluators, and focused tests
  config/      Research protocol, planned schedule, and analysis specifications
  schemas/     Machine-readable evidence and result contracts
  docs/        Detailed implementation and evidence documentation
data/pilot/    Selected pilot observations, attempt index, descriptive summary
docs/          Short guides to the study, tasks, pilot, and reproduction
```

## Quick check — no model account required

With **Python 3.12** and **Git** installed, run these commands from the repository root:

```sh
python -m benchmark.runner.verify_start_commits --verify
python -m unittest benchmark.runner.tests.test_api_wrapper benchmark.runner.tests.test_api_tools benchmark.runner.tests.test_openai_responses_transport benchmark.runner.tests.test_qwen_vllm_transport
```

The first command checks all 12 deterministic starting commits. The second exercises the API wrapper and logical tools with local test doubles; neither command calls a model provider. Docker and browser checks are documented separately in the [reproduction guide](docs/reproduction.md).

## Pilot and next release

The pilot validated execution, resets, evidence capture, and operational limits. All 16 selected records passed the common evidence validator; the eight selected native-IDE records also passed native validation. The pilot led to increasing the common API action limit from 15 to 30 before the main experiment.

Pilot outcomes are **descriptive process evidence**, excluded from the main dataset and unsuitable for system rankings. The next data release will contain the verified main run table, reported exclusions and replacements, analysis outputs, and final comparative figures.

Keep evaluated agents inside their assigned `workspaces/<run_id>/repo` directory. The full repository contains evaluator-only tests and oracle repairs that must remain outside the evaluated agent's information boundary.
