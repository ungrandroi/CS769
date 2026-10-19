"""Invoke the unchanged official BFCL whole-task scorer for one local Qwen run."""
import json
from pathlib import Path
import subprocess
import sys
import hashlib
from evaluate_qwen_compact import MODEL_KEY
ROOT = Path(__file__).resolve().parents[1]
def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value): path.write_text(json.dumps(value,indent=2)+"\n")

def score_run(directory, task):
    score_path = directory / "official-score.json"
    if score_path.exists():
        return read(score_path)
    result_paths = list((directory / "result").rglob(f"*{task['category']}_result.json"))
    assert len(result_paths) == 1, f"Missing/ambiguous official result at {directory}"
    rows = [json.loads(line) for line in result_paths[0].read_text().splitlines() if line.strip()]
    assert len(rows) == 1 and rows[0]["id"] == task["id"], "Refuse scoring duplicate/mismatched result"
    command = [sys.executable, str(ROOT / "scripts/evaluate_qwen_compact.py"), "evaluate", "--model", MODEL_KEY,
               "--test-category", task["category"], "--partial-eval", "--result-dir", str(directory / "result"),
               "--score-dir", str(directory / "score")]
    with (directory / "official-evaluation.log").open("w") as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    paths = list((directory / "score").rglob(f"*{task['category']}_score.json"))
    assert len(paths) == 1
    scores = [json.loads(line) for line in paths[0].read_text().splitlines() if line.strip()]
    assert scores[0]["total_count"] == 1 and scores[0]["correct_count"] in (0, 1)
    result = {"summary": scores[0], "passed": bool(scores[0]["correct_count"]),
              "diagnostics": [{k: v for k, v in row.items() if k in ("id", "valid", "error", "test_category", "model_name")} for row in scores[1:]],
              "result_sha256": sha(result_paths[0]), "score_sha256": sha(paths[0]),
              "evaluator": "official BFCL", "score_file": str(paths[0].relative_to(directory))}
    write(score_path, result)
    return result

