# CS769 — Graph Memory for Tool-Using Agents

This project studies graph memory for file-operation tasks in the Berkeley Function Calling Leaderboard (BFCL). Experiments use a locally hosted **Qwen3.8-27B-Q8_0** model and 26 task conditions: 13 task families evaluated under both `multi_turn_base` and `multi_turn_long_context`. The environment provides 18 simulated GorillaFileSystem tools, not a real Bash shell.

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

Each evaluated method has one run per task condition. These results are not estimates from repeated trials. Graph construction and serialization are implemented; a learned compressor and risk model are not yet implemented.

## Repository Layout

- `scripts/manage.py`: unified CLI for running experiments, auditing records, preparing checkpoints, probing codecs, and rendering reports.
- `scripts/workflows/`: experiment-specific workflows.
- `scripts/core/`: shared graph builders, codecs, model transport, scoring, batch scheduling, and frozen-source loading.
- `tests/`: unit tests and batch-safety checks.
- `experiments/bfcl_identity/qwen27b_experiment/`: complete early baseline records for 26 tasks and three methods.
- `experiments/bfcl_identity/v2_provenance_dedup_probe/`: offline Event Graph provenance-deduplication study.
- `experiments/bfcl_identity/qwen27b_dedup_eval/`: 26 evaluated Event Graph-Dedup continuations.
- `experiments/bfcl_identity/history1000_eval/`: prepared checkpoints for the pure 1,000-token history threshold.
- `experiments/bfcl_identity/reports/`: reports using the current method names.
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

# Run the test suite
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts scripts/bfcl_python.sh -m unittest discover -s tests -p 'test_*.py'
```

See the [CLI guide](scripts/README.md), [experiment usage notes](experiments/bfcl_identity/USAGE.txt), and [active experiment scope](experiments/bfcl_identity/ACTIVE_SCOPE.txt) for details. Some supporting documents remain in Chinese.

Download and open [the visualization page](visualization/index.html) in a browser to explore the saved results without calling a model. Dependencies for regenerating it are documented in the [visualization README](visualization/README.md).

## Reproducibility

The `source_code/` directories inside historical experiments contain frozen implementation snapshots. Preserve them together with their original records. Audit commands load these snapshots and write rebuilt reports separately, allowing active code to evolve without overwriting historical evidence.

Upstream BFCL code and tokenizer headers remain subject to their respective licenses.
