"""Record source identity without copying a runner or its dependencies."""
from pathlib import Path
import hashlib,json,subprocess
from importlib.metadata import version, PackageNotFoundError

def package_hashes():
    from cs769.base.paths import package_root, project_root, config_directory
    package=package_root();project=project_root()
    directories=[("src/cs769",package),("conf",config_directory())]
    directories += [(name, project/name) for name in ("base","datasets","models","tasks")]
    out={}
    for prefix, directory in directories:
        for p in sorted(directory.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py",".json") and "docs" not in p.relative_to(directory).parts:
                out[prefix+"/"+p.relative_to(directory).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return out

def source_identity():
    from cs769.base.paths import project_root
    root=project_root()
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
