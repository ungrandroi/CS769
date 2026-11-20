# 工具调用图记忆项目的公开入口

## 目的和主要功能

公开统一命令、配置与记忆准备接口，实际计算由职责目录直接提供。

## 适用范围

用于 `python -m cs769`、现有 Python 调用者和安装包入口。

实际组件说明见 [当前文档](../../doc/README.md)：数据归 `datasets/`，图记忆与模型归 `models/`，科研计算归 `tasks/`，公共协调归 `base/`，配方归 `conf/`。`configs/` 继续指向同一份配置。

`docs/source-manifest.json` 等文件保存历史迁移来源和当时哈希。新的运行源码身份由 `base/provenance.py` 记录当前所有职责目录与配方。
