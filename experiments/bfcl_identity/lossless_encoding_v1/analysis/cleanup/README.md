# Post-audit code organization

Completed after the independent final audit passed. This was a protective
cleanup of working entry points and documentation, with no new inference.

## Changes

- Connected the six public lossless workflow commands to the existing
  `scripts/manage.py` dispatcher; retained direct module imports and the
  internal postprocessing watcher.
- Rewrote `scripts/README.md` in English, separating historical protocols from
  the current native-working-input threshold and explaining each module's
  purpose. Report regeneration is explicitly distinguished from inspection;
  the documented frozen audit writes to `/tmp`, not existing evidence.
- Added the study's `RESULTS.md` and updated the main README with the completed
  study, exact results and limitations. Token reductions are relative to each
  graph control, while optimized inputs remain 40%/65%/55% above Identity.
- Added a narrowly scoped Git ignore rule for this study's machine-local
  frozen `vendor` symlinks; the links themselves were preserved.
- Corrected test instructions: the CLI needs BFCL runtime dependencies;
  pytest-style codec tests cannot be covered by unittest discovery alone.

No existing file was deleted. All seven lossless workflow modules have live
execution, audit, report or recovery roles. Consolidating these small modules
would add refactoring risk and compatibility wrappers without a meaningful
reduction in complexity. No unused temporary module was established, so none
was removed. Codec logic, model behavior and experimental configuration are
unchanged.

## Validation

- Four CLI tests passed in the BFCL conda environment.
- Twenty lossless codec tests passed in the host pytest environment.
- All six new CLI routes returned help successfully without inference.
- All 177 frozen source hash entries still match.
- File size/modification-time metadata matched before and after for 63,122
  protected files/symlinks across visualization, frozen source and run records.
  This metadata check supplements the completed independent audit; it is not
  a new content-hash audit of every trajectory.
- `git diff --check` passed, and all four machine-local snapshot vendor links
  are ignored by Git.

Initial attempts to combine tests in one existing interpreter exposed only
missing dependencies: the frozen conda environment lacks pytest, while host
Python lacks transformers. The appropriate suites then passed in their
respective existing environments. No environment was changed.

See `checks.json` and `git-status-before.txt` / `git-status-after.txt`.
No commit or push was performed. Trajectories, candidate registries, selection,
protocol, amendment, audit evidence, old experiments and `visualization/`
were not modified. The original controller terminal status remains untouched;
`runtime/agent-followup-plan.json` separately records final audit and cleanup
completion.
