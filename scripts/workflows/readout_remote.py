"""SSH-only transport for the five-arm readout validation (no public inference port)."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
from workflows import diagnostic_controller as checks


class RemoteService:
    def __init__(self, config, command, overrides, runtime, model, base_url):
        self.config, self.runtime, self.model = config, runtime, model
        self.ssh = config['ssh_command']
        port = base_url.rsplit(':', 1)[1].split('/')[0]
        checks.require(subprocess.run(self.ssh + ['true'], capture_output=True).returncode == 0, 'SSH connection failed')
        launch = {'command': command, 'env': dict(overrides, CUDA_VISIBLE_DEVICES='0'),
                  'pidfile': '/workspace/cs769-' + model + '.pid',
                  'log': '/workspace/cs769-' + model + '.log'}
        code = '''import json,os,subprocess,sys
from pathlib import Path
v=json.load(sys.stdin)
p=Path(v['pidfile'])
if p.exists(): raise RuntimeError('Existing remote launch; do not overwrite')
with open(v['log'],'xb') as f:
 c=subprocess.Popen(v['command'],env=dict(os.environ,**v['env']),stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
p.write_text(str(c.pid))
print(json.dumps({'pid':c.pid,'command':v['command']}))
'''
        # Put program in -c, while stdin carries JSON without shell interpolation.
        result = subprocess.run(self.ssh + ['python3 -c ' + shlex.quote(code)], input=json.dumps(launch), text=True, capture_output=True, check=True)
        self.remote = json.loads(result.stdout)
        self.remote['pidfile'] = launch['pidfile']
        checks.write(runtime / 'remote-server-launch.json', self.remote)
        self.stream = (runtime / 'tunnel.log').open('xb')
        self.tunnel = subprocess.Popen(self.ssh[:-1] + ['-N', '-L', f'127.0.0.1:{port}:127.0.0.1:{port}',
            '-o', 'ExitOnForwardFailure=yes', self.ssh[-1]], stdin=subprocess.DEVNULL,
            stdout=self.stream, stderr=subprocess.STDOUT, start_new_session=True)
        self.pid = self.tunnel.pid
        self.returncode = None

    def poll(self):
        return self.tunnel.poll()

    def terminate(self):
        # Terminate only the exact PID and executable started by this experiment.
        pid = self.remote['pid']
        code = '''import os,signal,sys
from pathlib import Path
pid=int(sys.argv[1]); expected=sys.argv[2]
cmd=Path('/proc')/str(pid)/'cmdline'
if cmd.exists():
 args=cmd.read_bytes().split(b'\\0')
 if args[0].decode()!=expected: raise RuntimeError('Remote PID ownership mismatch')
 os.kill(pid,signal.SIGTERM)
'''
        subprocess.run(self.ssh + ['python3 -c ' + shlex.quote(code) + ' ' + str(pid) + ' ' + shlex.quote(self.remote['command'][0])], check=True)
        self.tunnel.terminate()

    def wait(self, timeout=60):
        self.returncode = self.tunnel.wait(timeout=timeout)
        self.stream.close()
        return self.returncode


def verify_remote(config, contract):
    files = []
    for key in ['weights', 'model', 'server_binary', 'binary']:
        item = contract.get(key)
        if isinstance(item, dict) and 'sha256' in item and 'path' in item:
            files.append((item['path'], item['sha256']))
    code = '''import hashlib,json,sys
for path,expected in json.load(sys.stdin):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
 if h.hexdigest()!=expected: raise RuntimeError('Remote hash mismatch: '+path)
print('remote weights and executable hashes verified')
'''
    subprocess.run(config['ssh_command'] + ['python3 -c ' + shlex.quote(code)], input=json.dumps(files), text=True, check=True)
