# Supplementary Qwen interface control

Completed 26 October 2026. This experiment covers 12 tasks, three repetitions and two parser conditions: 72 valid selected runs. It is separate from the 144-run main comparison and appears in the [thesis](../docs/thesis/README.md), Methods §4.5, Results §5.6, Discussion §6.2 and Appendix E.

## What changed

Arm A used the frozen `qwen-fenced-tool-json-v3` compatibility parser. Arm B allowed physical newlines inside JSON objects. Both retained the single-call rule, supported tool names, argument checks, residual-text checks and refusal/finish handling. Model revision `c03e6d358207e414f1eca0bb1891e29f1db0e242`, vLLM 0.26.0, the chat template, prompts, task repositories, tools and sandbox were held fixed between arms.

Both arms used temperature 0, a 4,096-token output limit, 30 actions, a 180-second command timeout and a 5,400-second task timeout. Three consecutive responses without an accepted action triggered the no-progress stop. Separate guided prechecks verified real file reads, patches and command execution in both conditions. The formal runs used the original task prompts.

## Results

| Measure | A: frozen parser | B: multiline JSON |
|---|---:|---:|
| Valid runs | 36 | 36 |
| Task successes | 0/36 | 0/36 |
| Accepted tool calls | 29 | 52 |
| Accepted file reads | 18 | 25 |
| Accepted shell commands | 11 | 27 |
| Successful file or command operations | 0 | 3 |
| Tool errors | 29 | 49 |
| Nonempty final diffs | 0 | 0 |
| Model responses | 155 | 197 |

All 72 runs stopped at `protocol_no_progress_limit`. An accepted call passed parsing and dispatch; a successful operation returned without a tool error; task success required normal submission and all applicable checks. No patch or clarification request was accepted. B's three successful operations occurred in L2-02 repetition 3: `ls -la`, `ls -la app` and reading `app/main.py`.

| Task | A accepted calls | B accepted calls |
|---|---:|---:|
| L1-01 | 3 | 3 |
| L1-02 | 0 | 3 |
| L1-03 | 3 | 3 |
| L2-01 | 0 | 0 |
| L2-02 | 3 | 7 |
| L2-03 | 0 | 2 |
| L3-01 | 0 | 0 |
| L3-02 | 4 | 2 |
| L3-03 | 0 | 3 |
| L4-01 | 3 | 3 |
| L4-02 | 5 | 5 |
| L4-03 | 8 | 21 |

Each task had 0/3 successes in each arm. The three repetitions remain repeated observations of the same task.

## What the response audit shows

Replaying all 352 saved responses through both parsers produced 13 differences: A rejected a request that B accepted as a file read. Seven responses came from actual A trajectories and six from actual B trajectories. The six B responses occurred once in each repetition of L1-02 and L3-03. Every one requested a nonexistent path and failed when executed. The seven A responses establish counterfactual parsing acceptance only; no additional operations were executed.

The total difference of 29 versus 52 accepted calls also reflects different response trajectories and repeated failed commands. It cannot all be attributed to the newline rule. Among 81 accepted calls, 78 returned errors: 42 file-read errors, 30 shell exit codes of 127 and six shell exit codes of 1. Unavailable commands included `docker-compose` and `pytest`; the fixed sandbox was not changed during the control.

The audit matched all 36 pairs of initial requests after removing bookkeeping identifiers. All 352 responses reported fingerprint `vllm-0.26.0-607fd87d`, with zero native `tool_calls`.

Allowing multiline JSON removed a real parsing restriction but produced no completed tasks under these settings. The remaining failures involved paths, command availability and subsequent interaction as well as formatting. The control tests this one parser change; native tool calling and broader interface or environment changes remain untested.

## Selection and reproduction

Schedule position 51 (B, L4-03, repetition 1) was interrupted during its seventh request when the endpoint was paused. Its incomplete attempt was retained and excluded; a fresh attempt under the same configuration supplied that position's selected result. Each planned position is counted once. Prechecks are excluded.

The [72-row CSV and field guide](../data/qwen-interface-control/README.md) reproduce the run-level totals above. From the repository root:

```sh
python analysis/qwen_interface_summary.py
```

The command validates schedule coverage and prints totals without calling a model. The response-replay and detailed tool-error audit described above comes from the retained runtime evidence and Appendix E; the public CSV contains run-level counts, not the raw responses needed to rerun that audit. The original main dataset, scoring and Figures 8 to 16 are unchanged.
