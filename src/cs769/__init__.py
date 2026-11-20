"""目的和主要功能：公开 CS769 配置和记忆准备接口。

适用范围：源码布局及安装后的 cs769 命名空间；导入时登记科研方法。
"""
from pathlib import Path as _Path
# Source directories are installed under this namespace by setuptools.
_source_root = _Path(__file__).resolve().parents[2]
if (_source_root / "base/__init__.py").is_file():
    __path__.append(str(_source_root))
from cs769.base.config import ExperimentConfig, load_config
from cs769.tasks.memory import prepare
__all__ = ["ExperimentConfig", "load_config", "prepare"]
