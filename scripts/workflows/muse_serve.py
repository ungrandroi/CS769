"""Launch the pinned local Muse service without changing the Qwen service."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    root = Path(__file__).resolve().parents[2]
    runtime = root / 'experiments/bfcl_identity/muse_transfer_v1/runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / 'server-launch.json'
    if path.exists():
        raise SystemExit('Launch record exists; inspect existing service before restarting.')
    binary = Path('/tmp/ollama-upgrade-0.40.2/extracted/lib/ollama/llama-server')
    model = Path('/home/data/models/gguf/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf')
    overrides = dict(CUDA_VISIBLE_DEVICES='0',
                     GGML_BACKEND_PATH=str(binary.parent / 'cuda_v12/libggml-cuda.so'),
                     LD_LIBRARY_PATH=f'{binary.parent}/cuda_v12:{binary.parent}')
    env = dict(os.environ, **overrides)
    command = [str(binary), '--model', str(model), '--alias', 'bfcl-muse-glimmer-30b',
               '--host', '127.0.0.1', '--port', '11437', '--ctx-size', '131072',
               '--parallel', '1', '--n-gpu-layers', '99', '--flash-attn', 'on',
               '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0', '--jinja',
               '--chat-template-kwargs', '{"reasoning_strength":"low"}',
               '--reasoning-format', 'deepseek', '--no-reasoning-preserve',
               '--no-context-shift', '--threads', '8', '--batch-size', '1024',
               '--ubatch-size', '256', '--temp', '0.6', '--top-p', '0.95',
               '--top-k', '20', '--min-p', '0.05', '--repeat-penalty', '1.0']
    log = runtime / 'muse-server.log'
    with log.open('ab') as stream:
        proc = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True)
    record = dict(pid=proc.pid, command=command, cwd=str(root), env_overrides=overrides,
                  started_at=time.time(), log=str(log),
                  binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  version=subprocess.check_output([str(binary), '--version'], env=env,
                                                  stderr=subprocess.STDOUT, text=True),
                  detach='start_new_session; DEVNULL stdin; file-backed stdout/stderr')
    path.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
