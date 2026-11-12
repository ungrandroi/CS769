> 当前统一实验入口：`python -m cs769`。正式实现位于 `src/cs769/`；使用与迁移验证边界见 [docs/runtime.md](docs/runtime.md)。

# CS769 — Graph Memory for Tool-Using Agents

G9 integration: [guide](docs/g9-memory.md), [offline example](examples/g9_memory.py), and [maintained builder](src/cs769/g9.py). The original scripts/core imports remain compatible aliases.

This project studies graph memory for tool-using agents in BFCL. The maintained implementation is in src/cs769, with configurable graph builders, memory edits, model adapters, recovery and unchanged official evaluation. G9 replaces visible history with structured evidence; historical graph formats remain available as explicit configurations. The early file-system experiments below used Qwen and 18 simulated GorillaFileSystem tools, rather than a real Bash shell.

## Memory Methods

| Method | Historical ID | Representation |
|---|---|---|
| Identity | `identity` | Original message history |
| State-Transition Graph | `v1-compact` | State snapshot nodes connected by tool-call transition edges |
| Event Graph | `v2-compact` | Execution events, shared objects, and versioned facts |
| Event Graph-Dedup | `v2-dedup` | Lossless deduplication of repeated provenance relationships; individual tool calls remain distinct |

The graph methods use compact serialization. “Compact” means a more concise encoding of the full graph; it does not guarantee fewer tokens than the original message history. Historical IDs remain unchanged in stored artifacts for reproducibility.

## Experiment Reports

The [report index](experiments/bfcl_identity/reports/README.md) collects the [cross-experiment summary](experiments/bfcl_identity/reports/experiment-summary.md), V2–V5 readable reports, token accounting, and linked evidence. V2–V5 are historical stages; see the [G9 matched-118 report](experiments/bfcl_identity/reports/g9-event-matched118-results.md) for the later graph-replacement comparison. The early experiments below retain their original scope and results. Markdown is available for GitHub reading, alongside HTML views. Original experiment records and frozen source snapshots remain unchanged.

## Early experiments (historical)

| Experiment | Protocol | Status and results |
|---|---|---|
| Early baseline | Share the first Qwen-generated user turn, then replace history before the second user turn | 26 tasks per method. Official passes: Identity **18/26**, State-Transition Graph **14/26**, Event Graph **17/26** |
| Provenance deduplication: offline | Encode existing Event Graph memories and verify exact reconstruction | Offline serialization and token measurements; no model inference |
| Provenance deduplication: continuation | Continue from the same first-turn checkpoints using Event Graph-Dedup | Official passes: **15/26** |
| History threshold | Replace history when accumulated tool-call and return content reaches 1,000 tokens, excluding tool definitions | **prepared_not_run**: 9 tasks reach the threshold and 17 do not. No continuation scores yet |
| GPT-4.1 rerun | Early baseline protocol with Azure `gpt-4.1` generating every turn, including the first | Official passes: Identity **13/26**, State-Transition Graph **10/26**, Event Graph **11/26**. The graph drop also appears with GPT-4.1. See [the report](experiments/bfcl_identity/reports/gpt41_rerun.md) |
| GPT-5-mini rerun | Same protocol with Azure `gpt-5-mini`, `reasoning_effort` medium | Official passes: Identity **12/26**, State-Transition Graph **9/26**, Event Graph **9/26**. See [the report](experiments/bfcl_identity/reports/gpt5mini_rerun.md) and the [three-model summary](experiments/bfcl_identity/reports/model_comparison.md) |

Each evaluated method has one run per task condition. These results are not estimates from repeated trials. Graph construction and serialization are implemented; a learned compressor and risk model are not yet implemented.

## Repository Layout

- `src/cs769/`: maintained graph builders, edits, runtime, model/BFCL adapters, statistics and configurations.
- `scripts/manage.py`: compatibility launcher for the same CLI.
- `scripts/core/`: remaining compatibility imports; old workflows have been removed.
- `tests/`: tests of the maintained implementations; `tests/run.py` runs the free suite.
- `docs/`: current usage and migration notes.
- `experiments/bfcl_identity/`: historical records and reports; their source snapshots stay unchanged.
- `visualization/`: user-maintained memory replay interface.

## Setup

Clone the repository and its pinned BFCL submodule:

```bash
git clone --recurse-submodules https://github.com/ungrandroi/CS769.git
cd CS769
```

`vendor/gorilla` is pinned to the upstream commit used in the experiments. Exact Python environment records are provided in `experiments/bfcl_identity/conda-explicit.txt` and `experiments/bfcl_identity/requirements.lock.txt`. On a compatible Linux system:

```bash
conda create --prefix "$PWD/.conda/readable" --file experiments/bfcl_identity/conda-explicit.txt
scripts/bfcl_python.sh -m pip install -r experiments/bfcl_identity/requirements.lock.txt
scripts/bfcl_python.sh -m pip install -e . --no-deps
```

Lockfiles, frozen scripts, and runtime configurations may contain absolute paths from the original machine; adjust them when migrating to another system. BFCL source code is under `vendor/gorilla/berkeley-function-call-leaderboard/`. Follow its installation instructions to configure a local editable installation.

Model weights, inference-server binaries, the conda environment, and native tokenizer libraries are not included. Tokenizer versions and SHA-256 records are stored in `vendor/qwen-tokenizer-631109b34/`. Exact token counting and full validation require the matching native libraries and GGUF model path. Inference-server configurations are recorded in each experiment's `runtime/` directory. API credentials are excluded from the repository.

## Usage

```bash
# One runtime entry
scripts/bfcl_python.sh -B scripts/manage.py --help

# List profiles and validate a configuration
scripts/bfcl_python.sh -B -m cs769 list
scripts/bfcl_python.sh -B -m cs769 validate src/cs769/configs/g9-working-history.json

# Prepare graph input without model calls; output must be a new directory
scripts/bfcl_python.sh -B -m cs769 prepare --config src/cs769/configs/g9-working-history.json --history src/cs769/examples/history.json --output /tmp/cs769-input

# Run all free tests; actual network access is blocked
scripts/bfcl_python.sh -B tests/run.py
```

See the [runtime guide](docs/runtime.md) and [legacy removal notes](docs/legacy-removal.md). Paid runs require separately authorized budgets and private credential files. Old workflow commands are retired.

Open [the visualization page](visualization/index.html) to inspect saved results without model calls. Its source and data are unchanged.

## Reproducibility

The `source_code/` directories inside historical experiments contain frozen implementation snapshots. Preserve them together with their original records. The maintained replay command reads saved responses, re-executes the pinned official tools and evaluation, and writes any new outputs separately. It does not overwrite historical evidence.

Upstream BFCL code and tokenizer headers remain subject to their respective licenses.
