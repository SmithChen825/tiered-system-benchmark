# Tiered System Benchmark (TSB)

TSB tests how AI coding systems find and repair faults in web applications, from static websites to applications with a frontend, backend and database. The study compares four systems on 12 debugging tasks, with three fresh runs per system and task: 144 valid runs, including unsuccessful outcomes.

This repository contains the task suite, evaluation framework, experimental data and analysis for *Benchmarking Agentic Code Generation Tools*, a University of Melbourne thesis by Wenrui Chen, supervised by Prof. Richard Sinnott.

## Start here

- Read the [thesis PDF](docs/thesis/benchmarking-agentic-code-generation-tools.pdf), saved 24 October 2026. [Version details](docs/thesis/README.md) accompany the file.
- View the [results and figures](results/README.md).
- Download the [144-run dataset and field guide](data/main/README.md).
- Follow the [setup and reproduction guide](docs/reproduction.md).

## Main findings

Success requires a normal submission that passes every applicable functional and architectural check. The primary analysis uses reviewed scores; the original scores remain available for comparison.

| System | Successful runs | Success rate |
|---|---:|---:|
| Cursor | 35/36 | 97.2% |
| Devin Desktop | 33/36 | 91.7% |
| GPT-5.4 | 34/36 | 94.4% |
| Qwen2.5-Coder-7B-Instruct | 0/36 | 0% |

The task-paired tests found no statistically significant differences among Cursor, Devin Desktop and GPT-5.4 after correction for multiple comparisons. All three had higher success than the configured Qwen system. These findings concern the complete systems, including their interfaces, tools and execution controls, on these 12 tasks. They do not establish equivalence among the three higher-success systems or isolate the effect of the underlying models.

On the static-website tier (L1), Cursor, Devin Desktop and GPT-5.4 each succeeded in all nine runs. All nine Qwen runs stopped at the no-action response limit.

The [full analysis](results/README.md) reports results by task and tier, uncertainty intervals and paired comparisons. [Secondary results](results/secondary_results.md) cover elapsed time, diagnostic checks, clarification requests, L3/L4 success without evaluator responses, and the effect of score corrections. The [failure analysis](results/failure_analysis.md) examines all 42 reviewed unsuccessful runs.

## Study design

| Design | Scope |
|---|---|
| Systems | Cursor, Devin Desktop, GPT-5.4, Qwen2.5-Coder-7B-Instruct |
| Tasks | 12 debugging tasks across four architectural tiers |
| Main experiment | 12 tasks × 4 systems × 3 fresh repetitions = 144 runs |
| Pilot | 16 selected runs; 27 retained attempts in the audit index |
| Primary outcome | Normal submission with all required hidden tests and architectural checks passing |
| Other outcomes | Elapsed time, clarification behaviour, L3/L4 success without evaluator responses, and diagnostic test results |

### Four tiers of debugging

| Tier | Application | What the tasks exercise |
|---|---|---|
| L1 | Static website | Asset paths, responsive navigation, client-side validation |
| L2 | FastAPI application | Routing, requirement clarification, persistent storage |
| L3 | Vue + FastAPI | Cross-origin requests (CORS), response formats, API endpoint versions |
| L4 | Vue + FastAPI + PostgreSQL | Schema consistency, record creation, database connectivity |

Each task includes a public brief, a faulty starting repository, a reset to the same starting state, hidden evaluator tests and a known-good repair. Architectural checks verify that a repair preserves required properties of the application.

See the [task catalogue](docs/tasks.md), [experimental protocol](docs/protocol.md) and [analysis plan](benchmark/config/analysis_plan.main.json). For a concrete example, browse the [L3-03 brief](benchmark/tasks/L3-03/public_task_brief.md), [starting application](benchmark/tasks/L3-03/fixture_repo) and [task package](benchmark/tasks/L3-03).

## Data and scoring

The unified dataset contains success outcomes, timing and recorded behaviour for all 144 selected runs. Original and reviewed scores are stored separately. The [evaluation-review guide](docs/evaluation-review.md) explains the corrections and provides an offline script for reproducing the reviewed scores.

| Tier records | Included material |
|---|---|
| [L1](data/L1/README.md) | Results, individual checks, code diffs and attempt index |
| [L2](data/L2/README.md) | 36 selected runs, 38 retained attempts, checks, code diffs and exclusions |
| [L3](data/L3/README.md) | 36 selected runs, 38 retained attempts, original/reviewed scores, timing, checks and curated code diffs |
| [L4](data/L4/README.md) | 36 selected runs, 38 retained attempts, original/reviewed scores, timing, checks, final diffs and replacement records |

The pilot checked execution, resets, evidence capture and operational limits. All 16 selected records passed the common evidence validator; the eight selected native-IDE records also passed native validation. It led to increasing the common API action limit from 15 to 30 before the main experiment. Pilot outcomes describe the testing process and are excluded from the main analysis and system rankings. See the [pilot summary](docs/pilot.md), [selected observations](data/pilot/selected_runs.csv) and [attempt index](data/pilot/all_attempts.csv).

Full runtime archives and internal handoff notes remain outside the release. The [release scope](docs/release-scope.md) describes the published materials and their history.

## Reproduce the analysis and figures

Run `python analysis/build_dataset.py --check` to validate the unified dataset and `python analysis/failure_summary.py --check` to verify the failure summaries. These commands check the published outputs without rerunning the agents.

From the repository root, regenerate the nine quantitative figures:

```sh
python -m pip install -r analysis/requirements-statistics.txt
python analysis/plot_core_success.py
python analysis/plot_secondary_outcomes.py
```

Each figure has PDF, SVG and 300 dpi PNG exports. The [figure map and reproduction commands](results/README.md#thesis-figure-map) connect the files to thesis Figures 8 to 16. Figure 8a/b combines overall and task-level success; Figures 14 and 15 show failure stages and categories.

The [core notebook](analysis/core_success.ipynb) and [secondary notebook](analysis/secondary_outcomes.ipynb) reproduce the analyses. The [analysis manifest](results/core_success_manifest.json) records the numerical-analysis inputs and environment.

### Check the framework locally

With Python 3.12 and Git installed, run these commands from the repository root:

```sh
python -m benchmark.runner.verify_start_commits --verify
python -m unittest benchmark.runner.tests.test_api_wrapper benchmark.runner.tests.test_api_tools benchmark.runner.tests.test_openai_responses_transport benchmark.runner.tests.test_qwen_vllm_transport
```

The first command checks the starting commits for all 12 tasks. The second checks the API wrapper and logical tools with local test doubles. Neither requires a model account or calls a model provider. The [reproduction guide](docs/reproduction.md) also covers Docker and browser checks.

When running an evaluated agent, keep it inside its assigned `workspaces/<run_id>/repo` directory. Hidden evaluator tests and known-good repairs in the full repository must remain outside the agent's information boundary.

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
data/L3/       L3 original/reviewed results, timing, curated diffs, attempt index
data/L4/       L4 original/reviewed results, timing, final diffs, attempt index
data/main/     Unified 144-row analysis dataset, field guide, validation summary
analysis/      Dataset builder, statistical analysis, plotting scripts and tests
results/       Nine quantitative figures, captions, tables and failure evidence
data/evaluation-review/  144 paired scores, diagnostic evidence, review reproduction
data/pilot/    Selected pilot observations, attempt index, descriptive summary
docs/          Short guides to the study, tasks, pilot, and reproduction
docs/thesis/   Thesis PDF and version information
```
