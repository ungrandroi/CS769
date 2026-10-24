# Independent preflight: development amendment 1

**Pass. No blocking code or protocol issue found.** This review covers the development amendment and handoff; it is not final experimental sign-off.

The amendment adds minimal outer-explanation controls for Event Graph and Event Graph-Dedup, two codecs each. Registry v2 contains all ten prior configurations unchanged plus these four controls (14 total). This is an **adaptive development amendment**, motivated by observed State-Transition Graph explanation effects; it must not be called part of the original preregistration. At registration there were no Event/Dedup candidate attempts and no fresh-seed evaluation. Selection remains development-only and must freeze before fresh-seed evaluation.

Both snapshots validate against their hashes. Of the prior 42 scripts, only `lossless_controller.py` and `lossless_audit.py` changed. Controller changes add snapshot/registry/explanation-policy parameters and corresponding status fields. Audit changes strengthen direct payload and delivered-text verification. Model request paths, graph builders, codecs, sampling, threshold, tasks, seeds, and selection rule are byte-identical. Added analysis/postprocess/resume-guard scripts do not change model inputs.

The prelaunch strong guard passed for all 65 existing attempts before the v2 launch. Each retains its original v1 launch record. The in-flight v1 child completed before v2 started, and its completion is retained. V2 PID 1938875 reuses those 65 attempts and continues the next unfinished case. Its command, cwd and PYTHONPATH point to `source_code/candidates-v2`. The shared exclusive controller lock guards simultaneous controllers. No fresh evaluation was present at this audit.

An attempted independent guard rerun occurred after v2 had already resumed and correctly rejected the newly running attempt. This is expected fail-closed behavior; no files were changed by that failed check. The recorded prelaunch guard is the relevant handoff evidence.

Follow-ups: preserve the original registry, snapshot, pause/launch evidence and all scores; include amendment/registry hashes in restart validation. Continue distinguishing zero outer explanation from in-band codec instructions. Final independent audit remains required. Host process termination was not directly observable from this audit sandbox; launch/lock/progress evidence is consistent with safe handoff, with host verification supplied by the runner.

Machine-readable checks are in `preflight-amendment-1.json`.

Supplemental handoff check: `controller-v1-final-status.json` records supersession after current-task completion. All three amendment/registry hashes in `runtime/amendment-input-hashes.json` match. The runner additionally reports observing only a zombie child before terminating the paused parent; this host process observation is runner evidence, not a direct sandbox observation.
