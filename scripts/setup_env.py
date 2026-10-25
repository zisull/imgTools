# -*- coding: utf-8 -*-
"""按 env.json 补齐依赖：换电脑 clone 代码后的命令行入口。

    .venv\\Scripts\\python.exe scripts\\setup_env.py            # 装齐依赖 + 建目录
    .venv\\Scripts\\python.exe scripts\\setup_env.py --models   # 顺带把缺的权重也拉下来

必须用 .venv 里的 python 跑（体检看的就是「这个解释器装了些什么」）。
30GB 的权重默认不在这里下：打开壳在「环境与模型」页点「一键补齐」看得见进度，
真要命令行一把梭就加 --models。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webui"))

import env_check as ec  # noqa: E402


def main() -> int:
    with_models = "--models" in sys.argv
    print("解释器：%s" % sys.executable)
    try:
        r = ec.check(ROOT)
    except ec.SpecError as e:
        print("清单读不了：%s" % e)
        return 1
    todo = ec.fix_plan(r["items"], None if with_models else
                       [k for k in r["todo"] if not k.startswith("model:")])
    if not todo:
        print("环境已齐（依赖 + 目录%s）" % ("" if with_models else "，权重另说）"))
        return 0
    print("要补 %d 项：%s" % (len(todo), "、".join(x["label"] for x in todo)))
    bad = 0
    for it in todo:
        if it["fix"]["kind"] == "pip":
            argv = ec.pip_argv(it)
            print("\n$ %s" % " ".join(argv[2:]), flush=True)
            if subprocess.call(argv, cwd=ROOT):
                print("× %s 装失败：git 源要能连 github，直连不稳就先开代理再跑一次"
                      % it["label"])
                bad += 1
        elif it["fix"]["kind"] == "dir":
            os.makedirs(os.path.join(ROOT, *it["fix"]["path"].split("/")), exist_ok=True)
            print("建好目录 %s" % it["fix"]["path"])
        elif it["fix"]["kind"] == "model":
            print("\n开始下载 %s → %s（hf-mirror 断点续传，约 %s GB）"
                  % (it["fix"]["repo"], it["fix"]["name"], it.get("gb", "?")), flush=True)
            rc = subprocess.call([sys.executable, os.path.join(ROOT, "scripts", "dl_model.py"),
                                  it["fix"]["repo"], it["fix"]["name"]], cwd=ROOT)
            if rc:
                print("× 模型没下完：重跑这条命令会从断点继续")
                bad += 1
    left = ec.fix_plan(ec.check(ROOT)["items"], None)
    print("\n补全结束：失败 %d 项 · 还差 %d 项%s"
          % (bad, len(left), ("（%s）" % "、".join(x["label"] for x in left)) if left else ""))
    return 1 if (bad or left) else 0


if __name__ == "__main__":
    raise SystemExit(main())
