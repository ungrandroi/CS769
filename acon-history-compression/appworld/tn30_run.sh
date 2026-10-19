#!/bin/bash
set -u
cd /home/ruqi/public/acon/experiments/appworld
export APPWORLD_ROOT=/nobackup/ruqi/appworld
export PATH="/home/ruqi/miniconda3/envs/acon/bin:$PATH"
export PYTHONUNBUFFERED=1

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "OPENAI_API_KEY missing" >&2
  exit 1
fi

mapfile -t IDS < <(python -c 'import json; print("\n".join(t["id"] for t in json.load(open("selected_tasks.json"))["tasks"]))')
mkdir -p logs

{
  echo "=== START $(date -Is) ==="
  echo "python=$(command -v python)"
  python -c 'import productive_agents,inspect,os; import productive_agents.llm as m; print(m.__file__)'
  echo "APPWORLD_ROOT=$APPWORLD_ROOT"
  echo "n_tasks=${#IDS[@]}"
  echo "=== A tn30_nocomp $(date -Is) ==="
  python -u run_all.py --split test_normal --model_name gpt-4.1-mini --tag tn30_nocomp --task_ids "${IDS[@]}"
  echo "=== A exit $? $(date -Is) ==="
  echo "=== B tn30_prompting $(date -Is) ==="
  python -u run_all.py --split test_normal --model_name gpt-4.1-mini --tag tn30_prompting --co_config_path configs/context_opt/gpt-4.1-mini_history.yaml --task_ids "${IDS[@]}"
  echo "=== B exit $? $(date -Is) ==="
  echo "=== C tn30_ut $(date -Is) ==="
  python -u run_all.py --split test_normal --model_name gpt-4.1-mini --tag tn30_ut --co_config_path configs/context_opt/gpt-4.1-mini_history_ut.yaml --task_ids "${IDS[@]}"
  echo "=== C exit $? $(date -Is) ==="
  echo "=== ALL DONE $(date -Is) ==="
} 2>&1 | tee logs/tn30_run.log
