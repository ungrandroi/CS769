"""Uncompressed 200-question baseline with a thread bump and a token budget."""

import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path("/home/ruqi/public/gorilla/berkeley-function-call-leaderboard")
BFCL = "/home/ruqi/miniconda3/envs/bfcl/bin/bfcl"
LOG = ROOT / "logs/bfcl_long/run_baseline.log"
STATUS = ROOT / "logs/bfcl_long/baseline_status.json"
STOP = ROOT / "logs/bfcl_long/stop_baseline"
RESULT = (
    ROOT
    / "result_baseline200/gpt-4.1-mini-azure-FC/multi_turn/BFCL_v4_multi_turn_long_context_result.json"
)
STATS = ROOT / "logs/bfcl_stats/gpt-4.1-mini-azure-FC.baseline200.jsonl"
SCORE = (
    ROOT
    / "score_baseline200/gpt-4.1-mini-azure-FC/multi_turn/BFCL_v4_multi_turn_long_context_score.json"
)
CSV_PATH = ROOT / "baseline_200.csv"
MODEL = "gpt-4.1-mini-azure-FC"


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def count_429() -> int:
    if not STATS.exists():
        return 0
    n = 0
    for line in STATS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if json.loads(line).get("event") == "429":
            n += 1
    return n


def launch(threads: int, logf):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["BFCL_STATS_TAG"] = "baseline200"
    env["BFCL_INPUT_TOKEN_BUDGET"] = "15000000"
    env.pop("BFCL_HISTORY_MODE", None)
    env.pop("BFCL_DUMP_REQUESTS", None)
    env["BFCL_STOP_FILE"] = str(STOP)
    cmd = [
        BFCL,
        "generate",
        "--model",
        MODEL,
        "--test-category",
        "multi_turn_long_context",
        "--num-threads",
        str(threads),
        "--result-dir",
        "result_baseline200",
    ]
    logf.write(f"\n=== generate threads={threads} ===\n")
    logf.flush()
    return subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=logf, stderr=subprocess.STDOUT)


def budget_hit() -> bool:
    if not LOG.exists():
        return False
    return ">= budget" in LOG.read_text(encoding="utf-8", errors="replace")


def domain_of(test_id: str) -> str:
    num = int(test_id.rsplit("_", 1)[-1])
    if num < 50:
        return "filesystem"
    if num < 100:
        return "vehicle"
    if num < 150:
        return "trading"
    return "travel"


def fail_turn(err: dict):
    message = err.get("error_message")
    match = re.search(r"turn (\d+)", str(message))
    if match:
        return int(match.group(1)) + 1
    execution = err.get("execution_result")
    if isinstance(execution, list) and execution:
        return len(execution)
    if err.get("error_type") == "multi_turn:force_terminated":
        return 1
    return ""


def fail_check(err: dict) -> str:
    kind = err.get("error_type") or ""
    if "instance_state" in kind:
        return "state"
    if "execution_response" in kind:
        return "response"
    if "force_terminated" in kind:
        return "force_terminated"
    if "empty_turn" in kind:
        return "empty_turn"
    if "irrelevance" in kind:
        return "irrelevance"
    return kind or "other"


def write_csv():
    failures = {}
    for line in SCORE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "id" not in row:
            continue
        err = row.get("error") or {}
        failures[row["id"]] = err
    stats = {}
    for line in STATS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        bucket = stats.setdefault(
            row.get("id"),
            {"peak_api": 0, "messages_peak": 0, "tool_max": 0},
        )
        if row.get("event") == "agent":
            bucket["peak_api"] = max(bucket["peak_api"], row.get("input_tokens") or 0)
        elif row.get("event") == "messages_tokens":
            bucket["messages_peak"] = max(bucket["messages_peak"], row.get("tokens") or 0)
        elif row.get("event") == "tool":
            bucket["tool_max"] = max(bucket["tool_max"], row.get("tokens") or 0)
    rows = []
    for line in RESULT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        test_id = item["id"]
        token_lists = item.get("input_token_count") or []
        steps = 0
        for turn in token_lists:
            steps += len(turn) if isinstance(turn, list) else 1
        forced = "forced to quit" in json.dumps(item.get("inference_log"), ensure_ascii=False)
        err = failures.get(test_id)
        passed = err is None
        bucket = stats.get(test_id, {})
        rows.append(
            {
                "id": test_id,
                "domain": domain_of(test_id),
                "passed": int(passed),
                "fail_turn": "" if passed else fail_turn(err),
                "fail_check": "" if passed else fail_check(err),
                "force_terminated": int(forced or (not passed and fail_check(err) == "force_terminated")),
                "steps": steps,
                "peak_input_tokens": bucket.get("peak_api", 0),
                "messages_peak_tokens": bucket.get("messages_peak", 0),
                "max_tool_return_tokens": bucket.get("tool_max", 0),
            }
        )
    rows.sort(key=lambda row: int(row["id"].rsplit("_", 1)[-1]))
    header = [
        "id",
        "domain",
        "passed",
        "fail_turn",
        "fail_check",
        "force_terminated",
        "steps",
        "peak_input_tokens",
        "messages_peak_tokens",
        "max_tool_return_tokens",
    ]
    with CSV_PATH.open("w", encoding="utf-8") as handle:
        handle.write(",".join(header) + "\n")
        for row in rows:
            handle.write(",".join(str(row[key]) for key in header) + "\n")
    return len(rows)


def main():
    tert = ROOT / "logs/bfcl_long/test_case_ids_to_generate.tert10.json"
    if tert.exists():
        (ROOT / "test_case_ids_to_generate.json").write_text(tert.read_text(encoding="utf-8"))
    STOP.unlink(missing_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", encoding="utf-8") as logf:
        proc = launch(1, logf)
        bumped = False
        while proc.poll() is None:
            done = count_lines(RESULT)
            if done >= 20 and not bumped:
                n429 = count_429()
                logf.write(f"\n=== after {done} tasks, 429s={n429} ===\n")
                logf.flush()
                if n429 <= 2 * 20:
                    STOP.write_text("bump threads to 2\n", encoding="utf-8")
                    proc.wait()
                    STOP.unlink(missing_ok=True)
                    if budget_hit():
                        break
                    proc = launch(2, logf)
                bumped = True
            time.sleep(10)
        proc.wait()
        logf.write(f"\n=== generate exit {proc.returncode} lines {count_lines(RESULT)} ===\n")
        logf.flush()

    done = count_lines(RESULT)
    status = {
        "completed_tasks": done,
        "budget_hit": budget_hit(),
        "returncode": proc.returncode,
        "evaluated": False,
    }
    if done == 200 and not budget_hit() and proc.returncode == 0:
        with LOG.open("a", encoding="utf-8") as logf:
            logf.write("\n=== evaluate ===\n")
            logf.flush()
            eval_rc = subprocess.call(
                [
                    BFCL,
                    "evaluate",
                    "--model",
                    MODEL,
                    "--test-category",
                    "multi_turn_long_context",
                    "--result-dir",
                    "result_baseline200",
                    "--score-dir",
                    "score_baseline200",
                ],
                cwd=ROOT,
                stdout=logf,
                stderr=subprocess.STDOUT,
            )
        status["eval_returncode"] = eval_rc
        if eval_rc == 0 and SCORE.exists():
            status["csv_rows"] = write_csv()
            status["evaluated"] = True
    STATUS.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status), flush=True)


if __name__ == "__main__":
    main()
