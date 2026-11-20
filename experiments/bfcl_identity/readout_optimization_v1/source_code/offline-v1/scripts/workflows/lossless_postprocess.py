"""Persistent frozen postprocessing after inference, without touching runs."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time
from workflows.lossless_controller import read, write, verify


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    root=args.root.resolve()
    runtime=root/'runtime'
    lock=(runtime/'postprocess.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    path=runtime/'postprocess-status.json'
    status=dict(pid=os.getpid(),status='waiting_for_inference',started_at=time.time())
    write(path,status)
    try:
        while True:
            inference=read(runtime/'status.json')
            if inference['status']=='needs_review':
                raise RuntimeError('Inference requires review; no postprocessing or automatic retry')
            if inference['status']=='inference_complete_pending_independent_audit':
                break
            time.sleep(30)
        snapshot=Path(__file__).resolve().parents[2]
        verify(snapshot)
        status.update(status='mechanical_audit',updated_at=time.time())
        write(path,status)
        subprocess.run([sys.executable,'-m','workflows.lossless_audit','--root',str(root),
                        '--output',str(root/'reports/final-mechanical-audit.json')],check=True)
        status.update(status='paired_analysis',updated_at=time.time())
        write(path,status)
        subprocess.run([sys.executable,'-m','workflows.lossless_analysis','--root',str(root)],check=True)
        verify(snapshot)
        status.update(status='complete_pending_independent_review_and_cleanup',
                      finished_at=time.time())
    except BaseException as error:
        status.update(status='needs_review',error=repr(error),finished_at=time.time())
        raise
    finally:
        write(path,status)


if __name__=='__main__':
    main()
