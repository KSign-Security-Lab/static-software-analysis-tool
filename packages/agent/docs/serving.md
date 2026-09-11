# Serving a model

How the endpoint behind [`packages/agent`](../README.md) is configured, and which
models have been run against it.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `VLLM_MODEL` | `Qwen/Qwen3.8-27B-FP8` | Hugging Face id |
| `VLLM_GPUS` | `0` | Device ids, e.g. `0,1` |
| `VLLM_TP` | `1` | Tensor-parallel size; `2` with two GPUs |
| `HF_HOME` | `~/.cache/huggingface` | **Where weights are downloaded to** |
| `VLLM_TOOL_PARSER` | `qwen3_coder` | Tool-call parser; must match the model family |
| `VLLM_REASONING_PARSER` | `qwen3` | Only for models that think in-band; blank passes no flag |
| `VLLM_MAX_LEN` | `16384` | Must clear `AGENT_CONTEXT_CHARS` in tokens |
| `VLLM_MAX_SEQS` | `32` | Concurrent sequences; also caps CUDA-graph capture |
| `VLLM_MAX_BATCHED` | `8192` | Chunked-prefill budget; below the prompt size it stalls the decode batch |
| `VLLM_GPU_FRACTION` | `0.95` | What is left after the weights is KV cache, which is what bounds in-flight chunks |
| `VLLM_PORT` | `4403` | Host port; this project's band is 4400-4499, see `~/PORTS.md` |

The default is Qwen3.8-27B at FP8: about 31 GiB of weights, so one 48 GiB card
with `VLLM_TP=1`. FP8 wants sm89 or newer — on an Ampere card vLLM dequantises to
bf16 and the model no longer fits.

```bash
docker compose --profile vllm logs -f --tail 200 vllm
docker compose stop vllm                     # keep the container
docker compose --profile vllm rm -sf vllm    # remove it; the weights stay in HF_HOME
```

### Why vLLM runs in Docker

The host install cannot work: vllm 0.17 against torch 2.4, which predates
`torch.library.infer_schema`, and this workspace is on Python 3.14, which vLLM
does not publish wheels for.

## GPU layout — two cards, and whether it is worth it

Both GPUs can be used together: `VLLM_GPUS=0,1 VLLM_TP=2`. Whether it is worth it depends on
how the cards are wired, so measure rather than assume:

```bash
nvidia-smi topo -m                      # NV# means NVLink; NODE means PCIe only
python -c "import torch; print(torch.cuda.can_device_access_peer(0,1))"
```

On this host that reports `NODE` and `False`, so every tensor-parallel
all-reduce is staged through host memory. Without NVLink, add
`--disable-custom-all-reduce`: vLLM's custom all-reduce needs peer access.

Two more consequences when the cards are different generations, as they are
here (sm_89 Ada and sm_86 Ampere):

- **FP8 is unavailable.** It needs sm_89; the A6000 is sm_86. BF16/FP16 and
  INT4 AWQ/GPTQ run on both.
- **The slower card sets the pace.** Tensor parallelism splits work evenly, so
  the result is roughly twice an A6000, not Ada plus Ada.

So tensor parallelism here buys *capacity*, not speed: it is what makes a 32B at
FP16 possible at all. If a 4-bit 32B is good enough, one card is the better
trade — no interconnect cost, and it can be the faster one.

This used to be less of a constraint than it is now. The loop issued one request
at a time — callees before callers, so notes propagate — which kept batch size at
1 and made the missing NVLink barely matter. It no longer does: a round of chunks
times five specialists puts up to `AGENT_MAX_INFLIGHT` requests in flight at
once, which is what continuous batching is for and what makes the endpoint's
throughput rather than its latency the number that matters. Two independent
single-GPU servers behind one address now buy something real.

## Models this has been run against

Any model vLLM can serve works. Two things constrain the choice.

**It needs a tool-call parser for its family.** vLLM refuses tool calling without
one and the wrong one breaks it silently, which costs verification its tools —
the run falls back to context-only and says so once. It goes in `.env` beside
the model, because it cannot be guessed from the name. `vllm serve --help=all`
lists all 33: `hermes`, `qwen3_coder`, `mistral`, `llama3_json`, `llama4_json`,
`openai`, `deepseek_v3`, `glm45`, `glm47`, `granite`, `jamba`, `phi4_mini_json`,
`pythonic`, `kimi_k2`, `minimax`, `internlm`, `seed_oss`, `xlam` and more.

**It has to be big enough to finish the schema.** Guided decoding guarantees the
output *matches* the schema, not that the model ever finishes it. A model too
small for `ChunkAnalysis` emits a valid-so-far prefix until it runs out of room —
measured on a 0.5B, which spent 8048 tokens without closing the object.
`AGENT_MAX_TOKENS` bounds that into a fast, legible failure, and the log says
which model is at fault. Treat anything below about 7B as non-viable; a 4-bit 32B
is the sweet spot on a 48 GB card.

Every id below was checked against the Hugging Face API; it is a starting point,
not a whitelist.

| `VLLM_MODEL` | what it is | ~GiB | `VLLM_TOOL_PARSER` | `VLLM_REASONING_PARSER` | GPUs |
| --- | --- | --- | --- | --- | --- |
| `Qwen/Qwen3.8-27B-FP8` | thinking; needs an sm89+ card | 31 | `qwen3_coder` | `qwen3` | 1 |
| `Qwen/Qwen2.5-Coder-32B-Instruct-AWQ` | 4-bit code specialist | 19 | `hermes` | | 1 |
| `Qwen/Qwen2.5-Coder-14B-Instruct` | FP16 | 28 | `hermes` | | 1 |
| `mistralai/Devstral-Small-2507` | 24B, built for code agents | 48 | `mistral` | | 2 |
| `openai/gpt-oss-20b` | MXFP4 | 13 | `openai` | *(none: vLLM parses harmony itself)* | 1 |
| `openai/gpt-oss-120b` | MXFP4 | 61 | `openai` | *(none)* | 2 |
| `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct` | 16B MoE | 32 | `deepseek_v3` | | 1 |
| `meta-llama/Llama-3.1-8B-Instruct` | gated: needs `HF_TOKEN` | 16 | `llama3_json` | | 1 |
| `zai-org/GLM-4.5-Air` | 106B MoE | 60 | `glm45` | | 2 |
| `ibm-granite/granite-3.3-8b-instruct` | | 16 | `granite` | | 1 |
| `Qwen/Qwen2.5-0.5B-Instruct` | plumbing test only, finds nothing | 1 | `hermes` | | 1 |

A model wanting two GPUs needs `VLLM_TP=2` with it, or it fails to allocate.
