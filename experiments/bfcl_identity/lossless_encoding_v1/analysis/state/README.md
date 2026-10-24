# State-Transition Graph lossless representation candidates

The input is the complete delivered `readable-graph-1` JSON payload. `decode(encode(payload))` restores that payload directly without running any graph builder. Dictionary key order is not part of equality; list order, primitive types, source strings, event identities and every state are preserved. Exact source-history recovery and full original-graph rebuilding are checked additionally.

- `state-tables-v1`: homogeneous dictionaries become explicit columns, shared defaults and ordered rows. Object-row keys are stored explicitly. Tables are used only when they reduce character size by at least 20; native token measurements determine actual savings.
- `state-shared-v1`: adds an in-band dictionary for repeated exact strings/subtrees and explicit `$ref` references. The dictionary is literal, not recursively interned. Events/states remain separate rows even when some values share storage.
- `state-columnar-v1`: additionally groups source-message rows by schema and stores their original order. This candidate is retained as an offline attempt; its extra ordering and explanation overhead makes it less promising here.

All decoding conventions appear in `decoding` inside the delivered JSON and count toward model input. This is zero *external* explanation, not zero explanatory tokens. Literal marker collisions are escaped. There is no hidden dictionary, graph pruning, event merge, model-facing omission or summary.

## Development-only measurements

The 13 triggered old development checkpoints are selected exclusively from the registered six development conditions. They are not new model runs. Exact pinned local Qwen GGUF vocabulary tokenization gives mean memory-body tokens:

| Representation | Mean tokens | Ratio of means |
| --- | ---: | ---: |
| Original body | 4437.00 | 1.000 |
| Tables | 3991.69 | 0.900 |
| Tables + sharing | 4005.62 | 0.903 |
| Columnar + sharing | 4076.62 | 0.919 |

Rules, dictionary and envelope overhead are included. Fixed prompts, tool definitions, original external baseline explanation and native chat framing are excluded from these body-only counts; the live runner must count full requests separately. `measurements.json` includes all individual results, tokenizer provenance and input hashes. All 39 codec/checkpoint combinations pass direct payload, history and rebuilt-graph equality. Eight synthetic tests cover types, repeated distinct calls and literal tag collisions.

The first two candidates were handed to the unified inference runner. No capability, non-inferiority or task-performance claim follows from these offline results. Live development feedback is required before choosing or revising a candidate.

Reproduce from repository root:

```sh
PYTHONPATH=scripts python -m pytest -q tests/test_lossless_state.py
PYTHONPATH=scripts scripts/bfcl_python.sh experiments/bfcl_identity/lossless_encoding_v1/analysis/state/offline.py
```

The offline script writes measurement artifacts. Candidate readiness and live variant registration are owned by the agent handoff, so do not rerun it concurrently with registration.
