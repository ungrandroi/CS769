"""目的和主要功能：定位项目、默认配方和新实验目录。

适用范围：源码工作区的正常命令及安装后的配方读取。
"""
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
import cs769

def package_root():
    return Path(cs769.__file__).resolve().parent

def project_root():
    return package_root().parents[1]

def config_directory():
    candidate = project_root() / "conf"
    return candidate if candidate.is_dir() else package_root() / "configs"

def new_output(command):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return project_root() / "experiment" / command / (stamp + "_" + uuid4().hex[:8])
