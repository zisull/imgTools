"""从 hf-mirror 断点续传下载模型权重到 models/。

用法: python scripts/dl_model.py [repo_id] [local_dir_name]
默认下载 Qwen/Qwen-Image-2.1-Turbo。中断后重跑即续传。
"""
import os
import sys
import time

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from huggingface_hub import snapshot_download


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen-Image-2.1-Turbo"
    name = sys.argv[2] if len(sys.argv) > 2 else repo.split("/")[-1]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.join(root, "models", name)
    os.makedirs(target, exist_ok=True)

    for attempt in range(1, 21):
        try:
            snapshot_download(
                repo_id=repo,
                local_dir=target,
                max_workers=4,
                tqdm_class=None,
                etag_timeout=60,
            )
            print(f"DONE {repo} -> {target}", flush=True)
            return 0
        except Exception as exc:  # 网络瞬断/代理失效都靠重连续传兜住
            print(f"[retry {attempt}] {type(exc).__name__}: {exc}", flush=True)
            time.sleep(min(5 * attempt, 30))
    print("FAIL: exceeded retries", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
