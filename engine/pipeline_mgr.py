"""pipeline_mgr: QwenImage21Pipeline 单例管理。

12G 显存策略：BF16 + enable_model_cpu_offload（权重驻 32G 内存，按层流式上卡）。
Turbo checkpoint 自带 8 步 schedule，不传 steps 即官方推荐配置。
"""
from __future__ import annotations

import gc
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import torch

LogFn = Callable[[str], None]

# 官方分辨率预设（长边优先 2K 档）
ASPECT_RATIOS = {
    "1:1": (2048, 2048),
    "4:3": (2400, 1792),
    "3:4": (1792, 2400),
    "3:2": (2528, 1696),
    "2:3": (1696, 2528),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
}


@dataclass
class EngineState:
    loaded_repo: Optional[str] = None
    loading: bool = False
    busy: bool = False
    last_error: Optional[str] = None
    timings: list = field(default_factory=list)  # 最近 N 次生成耗时(秒)


class PipelineMgr:
    def __init__(self, log: LogFn = print):
        self.log = log
        self.state = EngineState()
        self.pipe = None

    def load(self, repo_path: str, offload: bool = True, quant: Optional[str] = None) -> None:
        """quant=None 全BF16(需大内存); quant="bnb8" 用 bitsandbytes int8 量化
        transformer+text_encoder，权重从 ~31GB 降到 ~17GB，避开 12G 显存/32G 内存双重 paging。"""
        if self.pipe is not None and self.state.loaded_repo == repo_path:
            return
        self.unload()
        from diffusers import QwenImage21Pipeline

        self.state.loading = True
        t0 = time.time()
        self.log(f"加载模型: {repo_path} (bf16{', bnb-int8' if quant == 'bnb8' else ''})")
        kwargs = {}
        if quant == "bnb8":
            from diffusers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
        try:
            pipe = QwenImage21Pipeline.from_pretrained(
                repo_path, dtype=torch.bfloat16, **kwargs
            )
            if offload:
                pipe.enable_model_cpu_offload()
            else:
                pipe.to("cuda")
        except Exception as exc:
            self.state.last_error = f"{type(exc).__name__}: {exc}"
            self.state.loading = False
            self.log(f"模型加载失败: {self.state.last_error}")
            raise
        self.pipe = pipe
        self.state.loaded_repo = repo_path
        self.state.loading = False
        self.log(f"模型加载完成，用时 {time.time() - t0:.1f}s")

    def unload(self) -> None:
        if self.pipe is None:
            return
        del self.pipe
        self.pipe = None
        self.state.loaded_repo = None
        gc.collect()
        torch.cuda.empty_cache()

    def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
        image=None,  # PIL.Image 或 list[PIL.Image]：编辑模式
        steps: Optional[int] = None,  # Turbo 留 None 走 checkpoint 内置 schedule
        seed: int = 42,
        kv_cache: bool = True,
    ):
        assert self.pipe is not None, "模型未加载"
        self.state.busy = True
        t0 = time.time()
        kwargs = dict(
            prompt=prompt,
            width=width,
            height=height,
            use_kv_cache=kv_cache,
            generator=torch.Generator("cpu").manual_seed(seed),
        )
        if image is not None:
            kwargs["image"] = image
        if steps is not None:
            kwargs["num_inference_steps"] = steps
        try:
            img = self.pipe(**kwargs).images[0]
        except torch.cuda.OutOfMemoryError as exc:
            self.state.last_error = f"CUDA OOM: {exc}"
            self.log("显存不足：请降一档分辨率或关闭其他占卡程序")
            raise
        finally:
            self.state.busy = False
        dt = time.time() - t0
        self.state.timings.append(round(dt, 1))
        del self.state.timings[:-20]
        self.log(f"生成完成 {width}x{height} 用时 {dt:.1f}s")
        return img

    def gpu_stats(self) -> dict:
        if not torch.cuda.is_available():
            return {}
        free, total = torch.cuda.mem_get_info()
        return {
            "vram_used_gb": round((total - free) / 2**30, 2),
            "vram_total_gb": round(total / 2**30, 2),
        }
