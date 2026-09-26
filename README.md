# Tiered System Benchmark (TSB)

**A controlled benchmark for testing how agentic coding systems diagnose and repair faults across frontend, backend, and database layers.**

TSB is the research software for *Benchmarking Agentic Code Generation Tools*, a University of Melbourne thesis by Wenrui Chen, supervised by Prof. Richard Sinnott.

Main collection is complete: **144 selected valid observations**, including valid unsuccessful outcomes. This branch retains the detailed [L1 results](data/L1/README.md) and [L2 results](data/L2/README.md), and adds a [uniform evaluator review](docs/evaluation-review.md) with original/reviewed scores for all 144 slots and an offline reproduction script. Full L3/L4 execution evidence and final comparative analysis are not included in this supplement.

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

## L1 results

Cursor, Devin Desktop, and GPT-5.4 each succeeded in 9/9 L1 runs. Qwen succeeded in 0/9, with all nine runs stopping at the no-action response limit. See the [L1 summary, per-run results, and attempt index](data/L1/README.md). These results cover the static-website tier only.

## L2 results

L2 includes 36 selected observations and 38 retained attempts. See the [L2 summary, check results, code diffs, and exclusions](data/L2/README.md).

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
data/L1/       L1 main results, check-level evidence, code diffs, attempt index
data/L2/       L2 original results, check-level evidence, code diffs, attempt index
data/evaluation-review/  144 paired scores, diagnostic evidence, review reproduction
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

## Pilot and remaining analysis

The pilot validated execution, resets, evidence capture, and operational limits. All 16 selected records passed the common evidence validator; the eight selected native-IDE records also passed native validation. The pilot led to increasing the common API action limit from 15 to 30 before the main experiment.

Pilot outcomes are **descriptive process evidence**, excluded from the main dataset and unsuitable for system rankings. The score-level review is now available for all 144 selected slots. The next data release will add the complete execution-level dataset, comparative analysis outputs, and final figures.

Keep evaluated agents inside their assigned `workspaces/<run_id>/repo` directory. The full repository contains evaluator-only tests and oracle repairs that must remain outside the evaluated agent's information boundary.
