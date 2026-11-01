# Tiered System Benchmark (TSB)

**How reliably can AI coding systems turn a debugging request into a working web application?**

TSB evaluates the complete repair workflow: reading a task, inspecting a repository, using tools, applying edits and submitting an application that meets its functional and architectural requirements. We compare **Cursor, Devin Desktop, GPT-5.4 and Qwen2.5-Coder-7B-Instruct** on **12 tasks across four architectural tiers**, with **144 valid main-experiment runs** and a separate **72-run Qwen interface control**.

This repository accompanies *Benchmarking Agentic Code Generation Tools*, a University of Melbourne thesis by **Wenrui Chen**, supervised by **Prof. Richard Sinnott**.

[📄 Read the thesis](docs/thesis/benchmarking-agentic-code-generation-tools.pdf) · [📊 Explore results](results/README.md) · [🗃️ Browse the dataset](data/main/README.md) · [🛠️ Setup guide](docs/reproduction.md)

## 🎯 Why this benchmark?

A completion score tells us whether a system passed an evaluator, but understanding a repair also requires knowing whether its tool requests executed, whether it changed the application and whether the evaluator assessed the stated requirements. Web applications add dependencies across frontend, backend, database and container boundaries; a local edit can leave the application contract unsatisfied.

TSB addresses the need to examine these dimensions together under controlled, inspectable conditions. It combines resettable application faults, shared task contracts, functional and architectural checks, a predefined clarification opportunity and versioned scoring evidence. This connects final outcomes to the repair process and to the acceptance conditions used to judge it. The [thesis, Section 2.7](docs/thesis/benchmarking-agentic-code-generation-tools.pdf) positions this design against prior work on repository repair, agent interfaces and clarification.

## ❓ Research questions

| RQ | Question |
|---|---|
| **RQ1 — Tiered task correctness** | How does task success change as debugging tasks progress from static websites to multi-container full-stack applications? |
| **RQ2 — Clarification-seeking behaviour** | When a predefined information gap is present, how often do evaluated systems request the required clarification, and how often do they make unnecessary requests on complete task briefs? |
| **RQ3 — Comparative system performance** | How do Cursor, Devin Desktop, GPT-5.4 and Qwen2.5-Coder-7B-Instruct differ in run-level success, execution time, clarification behaviour and success without evaluator clarification responses on L3/L4 tasks? |

## 🧪 What we built and completed

- **A 12-task benchmark:** public briefs, faulty starting repositories, deterministic resets, hidden functional tests, architectural checks and known-good repairs.
- **A shared evaluation framework:** run preparation, API execution and native-interface recording, evidence validation and final-state assessment.
- **A completed main comparison:** 12 tasks × 4 systems × 3 fresh repetitions = **144 selected valid runs**, including unsuccessful outcomes. The pilot is a separate dataset.
- **An auditable scoring review:** original and reviewed scores for the same runs, with the evidence and public-contract rationale for corrections.
- **A supplementary interface experiment:** 72 fresh Qwen runs comparing the frozen fallback with a parser accepting multiline JSON tool requests.
- **A reproducible analysis release:** run-level datasets, statistical scripts, notebooks, failure coding and nine quantitative figures with PDF, SVG and PNG exports.

### 🏗️ Four architectural tiers

| Tier | Application | Faults exercised |
|---|---|---|
| **L1** | Static website | Asset paths, responsive navigation, client-side validation |
| **L2** | FastAPI application | Routing, requirement clarification, persistent storage |
| **L3** | Vue + FastAPI | Cross-origin requests, response formats, API endpoint versions |
| **L4** | Vue + FastAPI + PostgreSQL | Schema consistency, record creation, database connectivity |

There are three tasks per tier. Each run starts from the assigned faulty state. **Success requires normal submission and every applicable functional and architectural check to pass.** Diagnostic check proportions are reported separately from binary success.

L2-02 contains the predefined information gap, with a fixed authorised clarification response. The other 11 briefs are complete. See the [task catalogue](docs/tasks.md), [protocol](docs/protocol.md) and [analysis plan](benchmark/config/analysis_plan.main.json). The [L3-03 task package](benchmark/tasks/L3-03) provides a concrete example.

## 📊 What we found

### ✅ System-level success

Reviewed scoring is the primary analysis; original scores remain available for sensitivity analysis.

| System | Successful runs | Success rate | Original successful runs |
|---|---:|---:|---:|
| Cursor | **35/36** | **97.2%** | 30/36 |
| GPT-5.4 | **34/36** | **94.4%** | 31/36 |
| Devin Desktop | **33/36** | **91.7%** | 31/36 |
| Qwen2.5-Coder-7B-Instruct | **0/36** | **0%** | 0/36 |

Exploratory task-paired comparisons over the 12 tasks distinguish each of the first three systems from the configured Qwen system after Holm adjustment across six comparisons. They do not distinguish the first three from one another; this result does not establish equivalence. The [full results](results/README.md) provide uncertainty intervals, task-level outcomes and paired comparisons.

![Reviewed success across systems and tasks](results/figures/success_summary.svg)

### 🔎 Findings by research question

- **RQ1:** Success does not decline monotonically across the selected architectural tiers. Cursor, Devin Desktop and GPT-5.4 pass all nine L1 runs each; remaining failures reveal task-specific contract violations. Tier and fault family vary together, so the task-level evidence explains the aggregate pattern.
- **RQ2:** GPT-5.4 requests and receives the authorised clarification in all three L2-02 repetitions. Cursor and Devin Desktop make no requests. Qwen makes eight unauthorised requests across two complete-brief runs. Completion and use of the clarification channel are distinct observed outcomes.
- **RQ3:** Alongside the success rates above, median elapsed time among successful runs is **27.01 s for GPT-5.4**, **102.27 s for Cursor** and **209.00 s for Devin Desktop**. These summaries describe each system's successful subset and configured workflow. On L3/L4, each of these three systems succeeds in **17/18** runs without evaluator clarification responses; Qwen succeeds in **0/18**. All L3/L4 runs received zero responses, so this metric coincides with success there.

See [secondary outcomes](results/secondary_results.md) for denominators, timing distributions and clarification measures, and [failure analysis](results/failure_analysis.md) for the 42 reviewed unsuccessful runs.

### 🔌 Supplementary Qwen interface control

Qwen's main-experiment final diffs are empty. The separate control compares the frozen fallback with a parser that accepts physical newlines inside JSON tool requests: **both arms achieve 0/36 successes**. The relaxed parser accepts additional requests, but newly accepted reads still encounter nonexistent paths. The experiment separates request parsing, tool execution and successful repair. Its 72 runs are analysed separately from the main comparison.

[Control results](results/qwen_interface_control.md) · [Control dataset](data/qwen-interface-control/README.md)

## 💬 What the results mean

**Execution is part of coding performance.** A proposed repair must pass through the configured interface and become an actual application change. The Qwen evidence locates failures before successful repair, while the other systems' unsuccessful submissions show how edits can still violate specific requirements.

**The acceptance contract shapes the result.** Scoring review changes ten success decisions and the descriptive ordering of the three higher-success systems. Their separation from Qwen persists under both scoring versions. Publishing both versions makes this sensitivity inspectable; the [review documentation](docs/evaluation-review.md) explains each correction.

**Clarification and completion answer different questions.** The predefined L2-02 opportunity records whether a system asks for missing intent; final-state checks establish whether its submission meets the resulting requirement. Their joint reporting preserves both behaviours.

These findings concern the recorded **end-to-end system configurations** on these tasks, including interfaces, tools and execution controls. The tier progression combines architecture and fault-family changes, and clarification evidence comes from one deliberately incomplete task. The thesis Discussion develops the implications for behavioural evaluation, contract-aligned checks and future benchmark coverage.

## 🔁 Reproduce the published results

### 📥 1. Get the repository and dependencies

Use Python 3.12 and Git. From a terminal:

```sh
git clone https://github.com/SmithChen825/tiered-system-benchmark.git
cd tiered-system-benchmark
python -m pip install -r analysis/requirements-statistics.txt
```

### 🧮 2. Validate the data and regenerate analyses

```sh
python analysis/build_dataset.py --check
python analysis/failure_summary.py --check
python analysis/core_success.py
python analysis/secondary_outcomes.py
python analysis/qwen_interface_summary.py
```

These commands use the published evidence and make no model-provider calls. The core and secondary scripts regenerate statistical tables and environment manifests; the supplementary script prints the two-arm summary. [Core](analysis/core_success.ipynb) and [secondary](analysis/secondary_outcomes.ipynb) notebooks provide an alternative entry point.

### 🖼️ 3. Regenerate the quantitative figures

```sh
python analysis/plot_core_success.py
python analysis/plot_secondary_outcomes.py
```

Outputs go to `results/figures/` as PDF, SVG and 300 dpi PNG files. The [figure map](results/README.md#thesis-figure-map) connects the nine figures to thesis Figures 8–16.

### 🧰 4. Check the framework and prepare new experiments

```sh
python -m benchmark.runner.verify_start_commits --verify
python -m unittest benchmark.runner.tests.test_api_wrapper benchmark.runner.tests.test_api_tools benchmark.runner.tests.test_openai_responses_transport benchmark.runner.tests.test_qwen_vllm_transport
```

These checks verify task starting states and exercise the API wrapper with local test doubles. For task validation, browser/Chromium setup, Docker Compose and PostgreSQL requirements, follow the [setup guide](docs/reproduction.md) and each task's instructions.

A new agent experiment also requires provider access, recorded native application versions, execution configuration and a validated freeze manifest. The curated release omits account credentials and private operational profiles; the setup guide explains the deployment steps. Keep the evaluated agent inside its assigned `workspaces/<run_id>/repo` directory, with hidden tests and known-good repairs outside its information boundary.

## 🗂️ Data and repository guide

| Location | Contents |
|---|---|
| [docs/thesis/](docs/thesis/README.md) | Final thesis PDF supplied as `thesisRevised36.pdf`, with version information |
| [benchmark/tasks/](benchmark/tasks) | Twelve briefs, fixtures, evaluators, repairs and validation instructions |
| [benchmark/runner/](benchmark/runner) | Run preparation, execution, recording and framework tests |
| [benchmark/config/](benchmark/config) | Task set, schedule, limits and analysis specifications |
| [data/main/](data/main/README.md) | Unified 144-run dataset and field guide |
| [data/L1/](data/L1/README.md), [L2/](data/L2/README.md), [L3/](data/L3/README.md), [L4/](data/L4/README.md) | Tier-specific checks, diffs and attempt records |
| [data/evaluation-review/](data/evaluation-review) | Paired scoring versions and review evidence |
| [data/qwen-interface-control/](data/qwen-interface-control/README.md) | Separate 72-run supplementary experiment |
| [data/pilot/](data/pilot) | Sixteen selected pilot runs and 27 retained attempts, excluded from main comparisons |
| [analysis/](analysis) | Dataset construction, statistics, plotting and notebooks |
| [results/](results/README.md) | Figures, tables, failure coding and analysis manifests |

The [release scope](docs/release-scope.md) describes the published evidence and archival boundaries. Full runtime archives and internal handoff notes remain outside the release.

## 📚 Reference and questions

When referring to this work, identify the thesis and the repository commit used:

> Chen, Wenrui. (2026). *Benchmarking Agentic Code Generation Tools*. University of Melbourne. Supervisor: Prof. Richard Sinnott.

Use [GitHub Issues](https://github.com/SmithChen825/tiered-system-benchmark/issues) for questions about tasks, data or reproduction, including the task/run identifier and relevant command output where applicable.
