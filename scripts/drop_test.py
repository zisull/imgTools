# -*- coding: utf-8 -*-
"""拖放/对话框回归：drop_path 四种候选形态 + 文件过滤串合法性。不启窗口。"""
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "webui"), os.path.join(ROOT, "engine")):
    sys.path.insert(0, _p)

from app import App, _IMG_FILTER  # noqa: E402


def main():
    # 1) 过滤串必须过 pywebview 的校验（空格分隔会被拒 → 对话框点了没反应）
    from webview.util import parse_file_type
    print("filter:", _IMG_FILTER)
    parse_file_type(_IMG_FILTER)

    a = App()
    out = os.path.join(ROOT, "outputs")
    os.makedirs(out, exist_ok=True)
    f = os.path.join(out, "拖放测试 中文.jpg")
    with open(f, "wb") as fh:
        fh.write(b"\xff\xd8\xff\xd9")
    try:
        enc = "file:///" + urllib.parse.quote(f.replace("\\", "/"), safe="/:")
        dlurl = 'file:///"%s"' % f
        cases = [
            ("原生绝对路径", [f]),
            ("file:/// 百分号编码", [enc]),
            ("DownloadURL 带引号", [dlurl]),
            ("斜杠形式", [f.replace("\\", "/")]),
            ("只有文件名(输出目录)", [os.path.basename(f)]),
            ("编码串在前+名字在后", [enc, os.path.basename(f)]),
        ]
        for name, cands in cases:
            r = a.drop_path(cands)
            ok = r.get("ok") and os.path.normpath(r["path"]) == os.path.normpath(f)
            print("%-22s -> %s %s" % (name, "PASS" if ok else "FAIL", r))
            assert ok, name
        bad = a.drop_path(["完全不存在的名.jpg", "file:///C:/nope/x.jpg"])
        print("%-22s -> %s %s" % ("全部落空", "PASS" if not bad["ok"] else "FAIL", bad))
        assert not bad["ok"] and bad.get("msg")
        d = a.drop_path([out])
        print("%-22s -> %s" % ("拖目录", "PASS" if d["ok"] else "FAIL"))
        assert d["ok"]
        n = a.drop_path(None)
        assert not n["ok"]
        print("空入参 PASS")

        # save_drop 兜底：前端把字节交回来代收
        import base64
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
        r1 = a.save_drop("我的 照片.jpg", "data:image/jpeg;base64," + png)
        print("%-22s -> %s" % ("save_drop 正常", "PASS" if r1.get("ok") and
                               os.path.isfile(r1["path"]) else "FAIL"))
        assert r1["ok"], r1
        r2 = a.save_drop("x.txt", "data:text/plain;base64," + png)
        assert not r2["ok"], r2
        r3 = a.save_drop("x.png", "不是dataurl")
        assert not r3["ok"], r3
        r4 = a.save_drop("x.png", "data:image/png;base64,@@bad@@")
        assert not r4["ok"], r4
        print("save_drop 负例 PASS")
        for k in (r1,):
            if k.get("path") and os.path.isfile(k["path"]):
                os.remove(k["path"])
    finally:
        os.remove(f)
    print("DROP TEST PASS")


if __name__ == "__main__":
    main()
