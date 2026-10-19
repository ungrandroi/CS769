import urllib.request,time,subprocess
from pathlib import Path
for port in (11435,11436):
 for _ in range(180):
  try:urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=2);break
  except Exception:time.sleep(1)
 else:raise RuntimeError(f'server {port} unavailable')
subprocess.run(['scripts/bfcl_python.sh','scripts/batch_qwen_dedup.py'],check=True)
