# -*- coding: utf-8 -*-
"""probe_h3_nodes.py —— 拉起内嵌 ComfyUI 问一遍 H3 相关节点的 API 契约，问完就杀。

为什么要真问：工作流模板里 class_type 与输入名写错一个字母，出图时只会得到
「未知 class_type」或节点报错，而体检看不出这种错。拿 /object_info 直接问最准。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "comfyui", ".venv", "Scripts", "python.exe")
MAIN = os.path.join(ROOT, "comfyui", "main.py")
PORT = 8899

WANT = [
    "UNETLoader", "CLIPLoader", "VAELoader", "LoraLoaderModelOnly", "LoadImage",
    "MiniMaxH3ImageToVideo", "EmptyMiniMaxH3LatentAV", "MiniMaxH3AddGuide",
    "MiniMaxH3ReferenceToVideo", "MiniMaxH3SigmaShift", "KSampler",
    "VAEDecode", "VAEDecodeAudio", "CreateVideo", "SaveVideo", "Record3D",
]


def wait_ready(proc, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False, "ComfyUI 提前退出，exit=%s" % proc.returncode
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/system_stats" % PORT, timeout=2) as r:
                if r.status == 200:
                    return True, ""
        except Exception:
            time.sleep(0.8)
    return False, "等 /system_stats 超时"


def main():
    si = None
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    log = open(os.path.join(ROOT, "logs", "probe_h3.log"), "wb")
    proc = subprocess.Popen([PY, MAIN, "--listen", "127.0.0.1", "--port", str(PORT),
                             "--disable-auto-launch", "--cpu"],
                            cwd=os.path.join(ROOT, "comfyui"),
                            stdout=log, stderr=subprocess.STDOUT,
                            creationflags=(0x08000000 if os.name == "nt" else 0))
    try:
        ok, why = wait_ready(proc)
        if not ok:
            print("READY FAIL:", why)
            return 1
        with urllib.request.urlopen("http://127.0.0.1:%d/object_info" % PORT, timeout=30) as r:
            info = json.load(r)
        out = {}
        for n in WANT:
            d = info.get(n)
            if not d:
                out[n] = None
                continue
            ins = d.get("input") or d.get("inputs") or {}     # /object_info 用的是单数 input
            out[n] = {"required": ins.get("required") or {},
                      "optional": ins.get("optional") or {},
                      "outputs": d.get("output", []),
                      "output_names": d.get("output_name", [])}
        path = os.path.join(ROOT, "logs", "probe_h3.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        for n, v in out.items():
            if v is None:
                print("MISSING NODE:", n)
                continue
            for sec in ("required", "optional"):
                for k, spec in v[sec].items():
                    types = spec.get("type")
                    if isinstance(types, list) and len(types) > 12:
                        types = types[:12] + ["…%d 项" % len(spec["type"])]
                    print("  %-24s %s %-16s %s" % (n, sec[:3], k,
                                                   json.dumps(types, ensure_ascii=False)[:200]))
            print("  %-24s out %s %s" % (n, v["outputs"], v["output_names"]))
        print("saved:", path)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
        log.close()


if __name__ == "__main__":
    sys.exit(main())
