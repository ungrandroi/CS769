"""Record source identity without copying a runner or its dependencies."""
from pathlib import Path
import hashlib,json,subprocess
from importlib.metadata import version,PackageNotFoundError

def package_hashes():
    root=Path(__file__).parent
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__"not in p.parts and p.suffix in (".py",".json") and "docs"not in p.relative_to(root).parts}
def source_identity():
    root=Path(__file__).resolve().parents[2]
    def git(*args):
        r=subprocess.run(["git","-C",str(root),*args],text=True,capture_output=True)
        return r.stdout.strip() if r.returncode==0 else None
    deps={}
    for name in ("openai","tiktoken","tokenizers","setuptools"):
        try:deps[name]=version(name)
        except PackageNotFoundError:deps[name]=None
    vendor=root/"vendor/gorilla"
    r=subprocess.run(["git","-C",str(vendor),"rev-parse","HEAD"],capture_output=True,text=True)
    return {"git_commit":git("rev-parse","HEAD"),"git_branch":git("branch","--show-current"),
            "package_sha256":package_hashes(),"dependencies":deps,"bfcl_vendor_commit":r.stdout.strip()if r.returncode==0 else None}
