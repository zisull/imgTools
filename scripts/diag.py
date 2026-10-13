"""诊断：确认各子模块所在设备 + 单步去噪耗时，定位 12G 溢出根因。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch  # noqa: E402

repo = os.path.join(ROOT, "models", "Qwen-Image-2.1-Turbo")

print("=== fp8(torchao) + enable_model_cpu_offload ===")
from diffusers import QwenImage21Pipeline
from diffusers.quantizers.pipe_quant_config import PipelineQuantizationConfig
from diffusers.quantizers.quantization_config import TorchAoConfig
from torchao.quantization import Float8WeightOnlyConfig
from transformers import TorchAoConfig as AoTf  # text_encoder 走 transformers 加载
from diffusers.quantizers.quantization_config import TorchAoConfig as AoDiff  # transformer 走 diffusers

pq = PipelineQuantizationConfig(quant_mapping={
    "transformer": AoDiff(quant_type=Float8WeightOnlyConfig()),
    "text_encoder": AoTf(quant_type=Float8WeightOnlyConfig()),
})
pipe = QwenImage21Pipeline.from_pretrained(repo, dtype=torch.bfloat16, quantization_config=pq)
pipe.enable_model_cpu_offload()
for name in ("transformer", "text_encoder", "vae"):
    m = getattr(pipe, name)
    p = next(m.parameters())
    print(f"{name:14} dtype={p.dtype} device={p.device} params={sum(x.numel() for x in m.parameters())/1e9:.2f}B")

free, total = torch.cuda.mem_get_info()
print(f"加载后显存: 用 {(total-free)/2**30:.2f}GB / {total/2**30:.2f}GB")

t0 = time.time()
img = pipe(prompt="a red cube", width=512, height=512, num_inference_steps=2,
           use_kv_cache=True, generator=torch.Generator("cpu").manual_seed(1)).images[0]
print(f"512/2步 用时 {time.time()-t0:.1f}s")
free, total = torch.cuda.mem_get_info()
print(f"生成后显存: allocated={torch.cuda.max_memory_allocated()/2**30:.2f}GB")
