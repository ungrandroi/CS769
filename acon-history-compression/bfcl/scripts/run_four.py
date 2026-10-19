"""Four reruns of the selected long tasks. No 15M budget. Threads follow the baseline rule."""

import os
import subprocess
import time
from pathlib import Path

ROOT = Path("/home/ruqi/public/gorilla/berkeley-function-call-leaderboard")
BFCL = "/home/ruqi/miniconda3/envs/bfcl/bin/bfcl"
LOG = ROOT / "logs/bfcl_long/run_four.log"
STOP = ROOT / "logs/bfcl_long/stop_four"

RUNS = [
    ("a2", "gpt-4.1-mini-azure-FC", "long_a2", "result_long_a2", "score_long_a2"),
    ("a3", "gpt-4.1-mini-azure-FC", "long_a3", "result_long_a3", "score_long_a3"),
    ("b", "gpt-4.1-mini-azure-hist-FC", "long_b", "result_long_b", "score_long_b"),
    ("c", "gpt-4.1-mini-azure-ut-FC", "long_c", "result_long_c", "score_long_c"),
]


def result_path(result_dir, model):
    return (
        ROOT
        / result_dir
        / model
        / "multi_turn/BFCL_v4_multi_turn_long_context_result.json"
    )


def stats_path(model, tag):
    return ROOT / "logs/bfcl_stats" / f"{model}.{tag}.jsonl"


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def count_429(path: Path) -> int:
    if not path.exists():
        return 0
    import json
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("event") == "429":
            n += 1
    return n


def launch(model, tag, result_dir, threads, logf):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["BFCL_STATS_TAG"] = tag
    env["BFCL_STOP_FILE"] = str(STOP)
    env.pop("BFCL_HISTORY_MODE", None)
    env.pop("BFCL_DUMP_REQUESTS", None)
    env.pop("BFCL_INPUT_TOKEN_BUDGET", None)
    cmd = [
        BFCL,
        "generate",
        "--model",
        model,
        "--run-ids",
        "--num-threads",
        str(threads),
        "--result-dir",
        result_dir,
    ]
    logf.write(f"\n=== {tag} threads={threads} ===\n")
    logf.flush()
    return subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=logf, stderr=subprocess.STDOUT)


def generate_one(name, model, tag, result_dir, logf):
    STOP.unlink(missing_ok=True)
    proc = launch(model, tag, result_dir, 1, logf)
    bumped = False
    result = result_path(result_dir, model)
    stats = stats_path(model, tag)
    while proc.poll() is None:
        done = count_lines(result)
        if done >= 20 and not bumped:
            n429 = count_429(stats)
            logf.write(f"\n=== {tag} after {done} tasks, 429s={n429} ===\n")
            logf.flush()
            if n429 <= 40:
                STOP.write_text(f"bump {tag}\n", encoding="utf-8")
                proc.wait()
                STOP.unlink(missing_ok=True)
                proc = launch(model, tag, result_dir, 2, logf)
            bumped = True
        time.sleep(10)
    proc.wait()
    logf.write(f"\n=== {tag} generate exit {proc.returncode} lines {count_lines(result)} ===\n")
    logf.flush()
    return proc.returncode


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", encoding="utf-8") as logf:
        for name, model, tag, result_dir, score_dir in RUNS:
            rc = generate_one(name, model, tag, result_dir, logf)
            if rc != 0:
                logf.write(f"\n=== {tag} skip eval after rc {rc} ===\n")
                continue
            logf.write(f"\n=== evaluate {tag} ===\n")
            logf.flush()
            subprocess.call(
                [
                    BFCL,
                    "evaluate",
                    "--model",
                    model,
                    "--test-category",
                    "multi_turn_long_context",
                    "--partial-eval",
                    "--result-dir",
                    result_dir,
                    "--score-dir",
                    score_dir,
                ],
                cwd=ROOT,
                stdout=logf,
                stderr=subprocess.STDOUT,
            )
        logf.write("\nFOUR_DONE\n")
    print("FOUR_DONE", flush=True)


if __name__ == "__main__":
    main()
