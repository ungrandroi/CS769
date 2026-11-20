"""目的和主要功能：共用 JSON 读取、结果创建、原子更新及文本计数。

适用范围：正常命令与任务的结果落盘；预算锁和任务指标由各自负责模块处理。
"""
import json
import os
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path,value):
    with Path(path).open("x") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)
        stream.write("\n")


def write(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    os.replace(temporary,path)


def counter(name):
    if name=="characters":return len
    import tiktoken
    encoding=tiktoken.get_encoding(name)
    return lambda text:len(encoding.encode(text,disallowed_special=()))
