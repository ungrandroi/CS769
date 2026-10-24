# Independent preflight audit

Status: **pass with follow-ups; no blocking protocol or codec defect found**. This is a code and partial-artifact review while inference is ongoing, **not the final experiment audit**.

Verified 78 independent strict round trips of the prior delivered `readable-graph-1` payloads across 13 triggered development prefixes and all six codecs. Decode restores the payload directly, preserves source-message ordering, and restores history; it does not substitute graph rebuilding for payload recovery. The current baseline matches all 39 corresponding prior selected payloads and explanations. Twenty codec tests and five protocol tests pass. All 42 frozen script hashes and four dataset hashes match.

At inspection time, three completed actual graph continuations passed native usage, sampler, checkpoint, prefix, and single-insertion checks; five untriggered manifests passed exclusion checks. The latter are **not graph-effect evidence**. Selection and new-seed evaluation had not begun.

The controller runs old development conditions (6 × 3 seeds) only before selection, writes an immutable selection, then creates fresh Identity histories with seeds 4409/5519/6637 before paired old-format and optimized continuations. The threshold is strictly >1000 native input tokens minus the same-request fixed baseline; complete call/return pairing is required. Conversion happens once, and the graph plus any outer explanation persist unchanged while new interactions append. Errors stop the controller; existing incomplete attempts are rejected. Conversion receives visible history only; future responses and evaluator state are not graph inputs.

Follow-ups:

- `none` means zero **outer** explanation. In-band `decoding`, `table_rule`, and `shared_rule` remain instructions to interpret the codec. They count in total input, but current `instruction_tokens` omits them. Final reporting must expose these costs and avoid treating nonadditive token fragments as exact additive partitions.
- Resume checks currently verify existing attempt status/task/seed, not all method, codec, explanation, source and configuration fields. Before any restart, require the runner's separate strong validation guard. Do not overwrite invalid attempts.
- Mechanical audit is insufficient for final sign-off: independently decode every real candidate memory; validate official scores, fixed-accounting samples, actual import/launch evidence and external dependency provenance. `vendor` is a symlink, not a frozen copy.
- Final reporting needs paired gain/loss counts against both current graphs and Identity, family/seed variation, and uncertainty. Development adoption by observed counts alone does not establish noninferiority.
- The controller performs a frozen candidate sweep, not an autonomous code-redesign loop. Review development failure and cost findings before deciding whether optimization is complete. Any new generation must use a new frozen snapshot.

Evidence and caveats are recorded in `preflight.json` and `preflight-evidence.json`; the independently runnable checker is `preflight_check.py`. Host PID inspection was unavailable within this audit sandbox, so the runner must supply host process evidence. No running source, historical experiment, or visualization code was modified.
