# -*- coding: utf-8 -*-
"""M3 端到端自测：真实载入模型，跑 图像编辑 / 局部编辑 / 透明素材 各一张并落盘。

直接驱动 webui/app.py 的 App._do_gen（与真壳同一条后端代码路径，跳过 pywebview 窗口），
按用户铁律：交付前自跑到终态、出真图，不靠 mock。
用法: .venv/Scripts/python.exe scripts/m3_selftest.py [edit|inpaint|rgba|all]
"""
import base64
import io
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webui"))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, os.path.join(ROOT, "webui", "ui"))

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

from app import App  # noqa: E402

BOAT = os.path.join(ROOT, "models", "Qwen-Image-2.1-Turbo", "assets", "turbo-boat-input.png")


def make_mask(path, box):
    """模拟前端画布导出的涂抹蒙版：透明底上画一块不透明矩形 = 要重绘区。"""
    from PIL import Image, ImageDraw
    im = Image.open(path)
    m = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(m).rectangle(box, fill=(255, 0, 0, 255))
    buf = io.BytesIO()
    m.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def run(app, tag, g):
    print("\n===== %s =====" % tag, flush=True)
    app._stop.clear()
    t0 = time.time()
    app._do_gen(g)
    dt = time.time() - t0
    assert app.st.get("last_image") and os.path.isfile(app.st["last_image"]), "没落盘成图"
    print("[%s] %.1fs -> %s" % (tag, dt, app.st["last_image"]), flush=True)
    return app.st["last_image"]


def main():
    which = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    app = App()
    app.cfg["console"]["model_dir"] = os.path.join("models", "Qwen-Image-2.1-Turbo")
    app.cfg["console"]["output_dir"] = "outputs"
    mgr = app._get_mgr()
    mgr.load(os.path.join(ROOT, "models", "Qwen-Image-2.1-Turbo"), offload=True, quant="fp8")
    app.st["model_loaded"] = True

    if which in ("edit", "all"):
        run(app, "edit", {
            "mode": "edit", "images": [BOAT], "res": "1024", "steps": "8", "seed": 20261009,
            "count": 1, "kv_cache": True,
            "prompt": "Create a photorealistic photograph of the motor yacht from the input "
                      "sketch, sailing on a calm deep-blue sea under a clear sky, full side "
                      "profile, black hull, white superstructure, yellow funnel.",
        })
    if which in ("inpaint", "all"):
        from PIL import Image
        w, h = Image.open(BOAT).size
        mask = make_mask(BOAT, (w // 3, h // 3, 2 * w // 3, 2 * h // 3))
        run(app, "inpaint", {
            "mode": "inpaint", "images": [BOAT], "mask": mask, "res": "512", "steps": "8",
            "seed": 7, "count": 1, "kv_cache": True,
            "prompt": "Replace the middle of the sketch with a bright red sail.",
        })
    if which in ("rgba", "all"):
        run(app, "rgba", {
            "mode": "rgba", "size": "512x512", "steps": "8", "seed": 42,
            "count": 1, "kv_cache": True,
            "prompt": "A flat vector icon of a lightbulb with a friendly face, isolated on a "
                      "fully transparent background, clean crisp edges, sticker style, no shadow.",
        })
    print("\nM3 自测全部通过", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
