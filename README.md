# CS769 — Graph Memory for Tool-Using Agents

This project studies graph memory for tool-using agents in the Berkeley Function Calling Leaderboard (BFCL), using a locally hosted **Qwen3.8-27B-Q8_0** model. The completed studies cover 13 filesystem-only task families and 37 additional families combining filesystem tools with Twitter, messaging, ticketing, or mathematics tools. These are simulated APIs, not a real Bash shell. Four conditions per family give 200 task-condition instances; repeated seeds are repetitions, not additional task families.

## Start Here

- [Experiment index](experiments/bfcl_identity/README.md): main results, historical baselines, development evidence, and exact record locations.
- [Combined 417-prefix results](experiments/bfcl_identity/combined_work1000/README.md): seven paired methods, source-study strata, input metrics, and links to original runs.
- [Filesystem optimization results](experiments/bfcl_identity/lossless_encoding_v1/RESULTS.md): completed and independently audited.
- [Mixed-tool expansion results](experiments/bfcl_identity/mixed_tool_expansion/independent_audit/final.md): completed and independently audited, including the Dedup regression and actual mixed-history subgroup.

The primary research directions are Identity and the selected State-Transition and Event encodings with short outer instructions. Keep their original-format controls and original Event Graph-Dedup for comparison. The newly optimized Dedup encoding remains a negative result, not the recommended default. No experiment is deleted because its score is unfavorable.

## Memory Methods

| Method | Historical ID | Representation |
|---|---|---|
| Identity | `identity` | Original message history |
| State-Transition Graph | `v1-compact` | State snapshot nodes connected by tool-call transition edges |
| Event Graph | `v2-compact` | Execution events, shared objects, and versioned facts |
| Event Graph-Dedup | `v2-dedup` | Lossless deduplication of repeated provenance relationships; individual tool calls remain distinct |

The graph methods use compact serialization. “Compact” means a more concise encoding of the full graph; it does not guarantee fewer tokens than the original message history. Historical IDs remain unchanged in stored artifacts for reproducibility.

## Experiments

| Experiment | Protocol | Status and results |
|---|---|---|
| Early baseline | Share the first Qwen-generated user turn, then replace history before the second user turn | 26 tasks per method. Official passes: Identity **18/26**, State-Transition Graph **14/26**, Event Graph **17/26** |
| Provenance deduplication: offline | Encode existing Event Graph memories and verify exact reconstruction | Offline serialization and token measurements; no model inference |
| Provenance deduplication: continuation | Continue from the same first-turn checkpoints using Event Graph-Dedup | Official passes: **15/26** |
| History threshold | Replace history when accumulated tool-call and return content reaches 1,000 tokens, excluding tool definitions | **prepared_not_run**: 9 tasks reach the threshold and 17 do not. No continuation scores yet |
| Working-history representation study | Convert once when native working input exceeds 1,000 tokens; select explanations on development histories | Completed precursor in `work1000_research/`; establishes the original-format controls for the next study |
| Lossless encoding optimization | Share Identity history; convert once when native working input exceeds 1,000 tokens, excluding fixed system/tool overhead | **Completed and independently audited.** Of 156 Identity repetitions, 120 trigger conversion. Paired successes: Identity **51/120**, optimized State **51/120**, Event **51/120**, Dedup **49/120**. [Results and limitations](experiments/bfcl_identity/lossless_encoding_v1/RESULTS.md) |
| Mixed-tool expansion | Freeze selected encodings; compare original and optimized formats over the same adapted semantic graphs | **Completed and independently audited.** 37 additional families, 148 conditions, 444 Identity repetitions, 297 triggered prefixes. Identity **120/297**; original → optimized: State **119 → 117**, Event **120 → 125**, Dedup **117 → 101**. [Audit and subgroup results](experiments/bfcl_identity/mixed_tool_expansion/independent_audit/final.md) |

The early baseline and deduplication continuation have one run per task condition. The newer lossless study uses repeated seeds and exact payload restoration, without pruning, semantic merging or summarization. Its optimized per-request inputs remain larger than Identity; equal aggregate successes do not prove equivalent ability. Graph construction and serialization are implemented; a learned compressor and risk model are not yet implemented.

Only 81 of the expansion's 297 converted prefixes actually contain non-filesystem calls. All three optimized methods have fewer successes than their own controls in that subgroup; the overall Event gain does not establish better mixed-history handling. Expansion to wholly non-filesystem task families remains future work.

## Repository Layout

- `scripts/manage.py`: unified CLI for running experiments, auditing records, preparing checkpoints, probing codecs, and rendering reports.
- `scripts/workflows/`: experiment-specific workflows.
- `scripts/core/`: shared graph builders, codecs, model transport, scoring, batch scheduling, and frozen-source loading.
- `tests/`: unit tests and batch-safety checks.
- `experiments/bfcl_identity/qwen27b_experiment/`: complete early baseline records for 26 tasks and three methods.
- `experiments/bfcl_identity/v2_provenance_dedup_probe/`: offline Event Graph provenance-deduplication study.
- `experiments/bfcl_identity/qwen27b_dedup_eval/`: 26 evaluated Event Graph-Dedup continuations.
- `experiments/bfcl_identity/history1000_eval/`: prepared checkpoints for the pure 1,000-token history threshold.
- `experiments/bfcl_identity/lossless_encoding_v1/`: completed repeated-seed encoding study, frozen candidates, request-level reports and independent audit.
- `experiments/bfcl_identity/mixed_tool_expansion/`: completed mixed-tool evaluation, semantic adapters, frozen records and independent final audit.
- `experiments/bfcl_identity/reports/`: historical-baseline reports using the current method names; newer studies keep their own `reports/` directories.
- `visualization/`: user-maintained memory replay interface, including source files and a standalone `index.html`.

## Setup

Clone the repository and its pinned BFCL submodule:

```bash
git clone --recurse-submodules https://github.com/ungrandroi/CS769.git
cd CS769
```

`vendor/gorilla` is pinned to the upstream commit used in the experiments. Exact Python environment records are provided in `experiments/bfcl_identity/conda-explicit.txt` and `experiments/bfcl_identity/requirements.lock.txt`. On a compatible Linux system:

```bash
conda create --prefix "$PWD/.conda/bfcl" --file experiments/bfcl_identity/conda-explicit.txt
scripts/bfcl_python.sh -m pip install -r experiments/bfcl_identity/requirements.lock.txt
```

Lockfiles, frozen scripts, and runtime configurations may contain absolute paths from the original machine; adjust them when migrating to another system. BFCL source code is under `vendor/gorilla/berkeley-function-call-leaderboard/`. Follow its installation instructions to configure a local editable installation.

Model weights, inference-server binaries, the conda environment, and native tokenizer libraries are not included. Tokenizer versions and SHA-256 records are stored in `vendor/qwen-tokenizer-631109b34/`. Exact token counting and full validation require the matching native libraries and GGUF model path. Inference-server configurations are recorded in each experiment's `runtime/` directory. API credentials are excluded from the repository.

## Usage

```bash
# Show available commands
scripts/bfcl_python.sh scripts/manage.py --help

# Audit the existing baseline without model inference
scripts/bfcl_python.sh scripts/manage.py audit baseline

# Prepare a new history-threshold batch without model inference
scripts/bfcl_python.sh scripts/manage.py run history1000 --prepare-only --output /tmp/history-check

# Check CLI routes in the BFCL runtime environment
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts scripts/bfcl_python.sh -m unittest discover -s tests -p 'test_cli.py'

# Check lossless codecs in a Python environment with pytest
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 -m pytest -q tests/test_lossless_state.py tests/test_lossless_event.py
```

See the [CLI guide](scripts/README.md), [experiment usage notes](experiments/bfcl_identity/USAGE.txt), and [active experiment scope](experiments/bfcl_identity/ACTIVE_SCOPE.txt) for details. Some supporting documents remain in Chinese.

Download and open [the visualization page](visualization/index.html) in a browser to explore the saved results without calling a model. Dependencies for regenerating it are documented in the [visualization README](visualization/README.md).

## Reproducibility

The `source_code/` directories inside historical experiments contain frozen implementation snapshots. Preserve them together with their original records. Audit commands load these snapshots and write rebuilt reports separately, allowing active code to evolve without overwriting historical evidence.

Upstream BFCL code and tokenizer headers remain subject to their respective licenses.
