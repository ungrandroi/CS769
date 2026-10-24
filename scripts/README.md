# Experiment CLI

Use `scripts/bfcl_python.sh scripts/manage.py ...` from the repository root.
The launcher uses the local `.conda/bfcl` environment. Commands import their
workflow lazily; historical module entry points remain available.

```text
scripts/
  manage.py                 Shared command dispatcher
  bfcl_python.sh            Conda environment launcher
  core/                     Graph builders, codecs, transport and scoring
  workflows/                Protocol-specific execution and analysis
  local_qwen_tokenizer.py    Compatibility import used by visualization
  qwen_prompt_accounting.py Compatibility import used by visualization
```

## Methods and protocols

| Method | Core module | Historical ID |
|---|---|---|
| Identity | Original message history | `identity` |
| State-Transition Graph | `core/state_transition_graph.py` | `v1-compact` |
| Event Graph | `core/event_graph.py` | `v2-compact` |
| Event Graph-Dedup | `core/event_graph_dedup.py` | `v2-dedup` |

Display names are defined in `core/research_modes.py`. Historical IDs and
frozen paths remain unchanged. Deduplication preserves individual tool calls.
The latest lossless codecs are `core/lossless_state.py` and
`core/lossless_event.py`; the latter handles Event Graph and Event Graph-Dedup.

Protocols are distinct from methods:

- `baseline`: conversion after the first user turn.
- `dedup`: provenance-deduplication continuation from those checkpoints.
- `history1000`: the earlier prepared call-and-return threshold experiment.
- `lossless`: repeated-seed optimization of `readable-graph-1` payloads after
  native working input exceeds 1,000 tokens. Fixed system/tool overhead is
  excluded; dynamic messages and their wrappers count toward this threshold.
- `work1000_*` modules: the completed representation/explanation study preceding
  the lossless codecs. Its frozen results provide the development controls.
- `mixed_*` modules: the completed expansion to 37 additional mixed-tool task
  families, using audited domain adapters and the previously selected codecs.

For main results and archived experiments, start with the
[experiment index](../experiments/bfcl_identity/README.md). Module names are kept
stable for replay; historical entry points are not evidence of active jobs.

## Common commands

```bash
scripts/bfcl_python.sh scripts/manage.py --help
scripts/bfcl_python.sh scripts/manage.py checkpoints
scripts/bfcl_python.sh scripts/manage.py run history1000 --prepare-only --output /tmp/history-check
scripts/bfcl_python.sh scripts/manage.py audit baseline
scripts/bfcl_python.sh scripts/manage.py audit dedup
scripts/bfcl_python.sh scripts/manage.py probe dedup
scripts/bfcl_python.sh scripts/manage.py reports
```

`bfcl` forwards to the official CLI. Internal `task` routes run individual
cases and are normally called by batch controllers.

## Lossless study entry points

The completed study is documented in
[RESULTS.md](../experiments/bfcl_identity/lossless_encoding_v1/RESULTS.md).
Its recorded protocol, candidate selection and source snapshots are frozen.

| Command | Module | Purpose |
|---|---|---|
| `run lossless` | `lossless_controller` | Serial development, selection and fresh paired evaluation |
| `task lossless` | `lossless_task` | Codec validation and one continuation |
| `audit lossless` | `lossless_audit` | Read records; write checks to an explicit `--output` |
| `report lossless` | `lossless_report` | Rebuild `reports/summary.json` |
| `analyze lossless` | `lossless_analysis` | Rebuild paired statistics and request/turn CSVs |
| `guard lossless` | `lossless_resume_guard` | Validate configuration before restarting a stopped controller |

All take `--root`; the controller also requires `--project`. Use `--help`
for exact arguments. `lossless_postprocess` is the internal detached watcher
that invokes audit and analysis after inference. These seven small modules
have distinct responsibilities and retain the import paths used by snapshots.

For the completed study, read existing reports rather than regenerating them.
`report` and `analyze` overwrite derived files; use a separate study copy for
exploratory changes. To repeat mechanical validation against frozen code and
write a separate output, run from the repository root:

```bash
PYTHONPATH=experiments/bfcl_identity/lossless_encoding_v1/source_code/postprocess-v2/scripts \
  scripts/bfcl_python.sh -m workflows.lossless_audit \
  --root experiments/bfcl_identity/lossless_encoding_v1 \
  --output /tmp/lossless-audit.json
```

Resumption requires confirming that the old controller is stopped, passing
the configuration guard, and using the exact recorded launch configuration.
Do not start a new controller against a completed study merely to inspect it.
No score-based retry or overwrite is allowed. New studies need a separate
root, registered configuration and fresh source snapshot.

Frozen `source_code/*/vendor` links point to this machine's vendor directory;
this study's links are ignored by Git. Preserve the local links and recreate
appropriate links when migrating a copy. Never commit credentials, model
weights, environments or machine-local caches. Preserve all trajectories,
frozen source and user-maintained `visualization/` code.

## Mixed-tool study entry points

The completed expansion's [final audit](../experiments/bfcl_identity/mixed_tool_expansion/independent_audit/final.md)
is the authoritative result. Direct module entry points remain available; they
are not currently registered in `manage.py`:

| Module | Purpose |
|---|---|
| `workflows.mixed_controller` | Frozen development/review gates and paired evaluation |
| `workflows.mixed_task` | One Identity or graph continuation using mixed-domain adapters |
| `workflows.mixed_audit` | Mechanical checks with a separate output destination |
| `workflows.mixed_report` | Rebuild summary and paired statistics; overwrites derived reports |

Inspect options without model generation:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=experiments/bfcl_identity/mixed_tool_expansion/source_code/adapters-v1/scripts \
  scripts/bfcl_python.sh -m workflows.mixed_audit --help
```

`core/mixed_observations.py`, `mixed_state_graph.py`, `mixed_event_graph.py` and
`mixed_graph.py` implement the shared semantic adapters and delivered payloads.
Original-format and optimized arms use the same adapted graph. Their comparison
does not isolate the adapter effect; domain coverage is explicitly audited.
These modules and the one-off independent audit scripts still support
reproduction and are retained. Do not remove them merely because inference has
finished. Full histories and snapshot paths stay unchanged.

## Tests

The combined fresh-evaluation index can be rebuilt without BFCL dependencies or
model inference. It reads completed source manifests and summaries, validates
matching boundaries/configurations, and writes only into a new or empty directory:

```bash
python scripts/workflows/combined_report.py --output /tmp/bfcl-combined-review
```

The checked-in index is under `experiments/bfcl_identity/combined_work1000/`.
Its rows point to original runs rather than duplicating trajectories. Preserve
source-study labels when analyzing the pooled 417 prefixes.

The BFCL conda environment has the runtime dependencies. Codec tests also
require `pytest`, which is available in the host Python environment on the
experiment machine but not installed in the frozen BFCL environment.

```bash
# CLI routes and argument forwarding, using BFCL runtime dependencies
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts \
  scripts/bfcl_python.sh -m unittest discover -s tests -p 'test_cli.py'

# Pure codec tests, using a Python environment with pytest
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts \
  python3 -m pytest -q tests/test_lossless_state.py tests/test_lossless_event.py
```

Running the entire suite with pytest requires both pytest and the BFCL
runtime dependencies in the same environment; unittest discovery alone does
not execute pytest-style test functions.
