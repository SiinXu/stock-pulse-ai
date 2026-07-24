# Local Model Catalog

StockPulse keeps its curated local-model business data in
`src/llm/local_model_catalog.json`. The backend validates and exposes that file.
The desktop main process derives its pull allowlist from the same file and
passes an inert projection to the sandboxed preload. Do not add a second model
list in Python, JavaScript, or UI code.

The facts below were verified on 2026-07-23. Artifact sizes use decimal GB,
matching Ollama's display. RAM values are conservative StockPulse operating
guidance for running the model beside the desktop app; they are not vendor
guarantees and context length can increase memory use.

## General Models

| Catalog ID | Pull tag | Q4_K_M download | RAM guidance | License | Role |
| --- | --- | ---: | ---: | --- | --- |
| `qwen3-4b` | `qwen3:4b` | 2.50 GB | 8 GB | Apache-2.0 | Lightweight |
| `qwen3-8b` | `qwen3:8b` | 5.23 GB | 16 GB | Apache-2.0 | Default |
| `gemma4-12b` | `gemma4:12b` | 7.56 GB | 24 GB | Apache-2.0 | High-capacity multimodal |
| `deepseek-r1-8b` | `deepseek-r1:8b` | 5.23 GB | 16 GB | MIT | Reasoning-focused |

Primary evidence:

- [Qwen3 4B on Ollama](https://ollama.com/library/qwen3:4b) is a real
  `Q4_K_M` tag with a 2,497,280,480-byte model layer. Its embedded license and
  the [Qwen3 4B upstream license](https://huggingface.co/Qwen/Qwen3-4B/blob/main/LICENSE)
  are Apache-2.0.
- [Qwen3 8B on Ollama](https://ollama.com/library/qwen3:8b) is a real
  `Q4_K_M` tag with a 5,225,374,496-byte model layer. Its embedded license and
  the [Qwen3 8B upstream license](https://huggingface.co/Qwen/Qwen3-8B/blob/main/LICENSE)
  are Apache-2.0.
- [Gemma 4 12B on Ollama](https://ollama.com/library/gemma4:12b) exists; no
  substitute is needed. Its `Q4_K_M` model layer is 7,381,382,048 bytes and its
  required projector is 175,115,584 bytes, for 7,556,497,632 bytes in total.
  The current manifest requires Ollama 0.30.5 and embeds the
  [Apache-2.0 license](https://ollama.com/library/gemma4:12b/blobs/0d542e0c8804).
- [DeepSeek-R1 8B on Ollama](https://ollama.com/library/deepseek-r1:8b) is a
  real `Q4_K_M` tag with a 5,225,373,760-byte model layer. The current tag is
  the 8.2B Qwen3-family
  [DeepSeek-R1-0528-Qwen3-8B](https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B),
  not the older Distill-Qwen-7B snapshot, and it embeds the same MIT text as
  the [official upstream license](https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B/blob/main/LICENSE).

### Llama 3.2 3B Retirement

`llama3.2:3b` is no longer a recommended desktop preset. The Llama 3.2
Community License permits redistribution but adds obligations beyond a normal
permissive-license notice: distributors must provide the agreement, retain a
specific NOTICE, and prominently display "Built with Llama". Qwen3 4B covers
the lightweight tier under Apache-2.0, so retaining Llama 3.2 would enlarge the
product compliance surface without filling a catalog gap. Existing user
installations remain ordinary Ollama models; this change only removes the
StockPulse recommendation and pull allowlist entry.

## Finance Models

All three fixed finance selections remain in the catalog. A catalog entry is
not a claim that StockPulse currently hosts its weights.

| Catalog ID | Verified upstream | Q4_K_M evidence | License conclusion | Distribution status |
| --- | --- | ---: | --- | --- |
| `dianjin-r1-7b` | HF `DianJin/DianJin-R1-7B`; ModelScope `tongyi_dianjin/DianJin-R1-7B` | Community GGUF, 4.68 GB | MIT metadata; no standalone file | Convert official weights, then publish with MIT notice |
| `fin-r1-7b` | HF `SUFE-AIFLM-Lab/Fin-R1`; no official ModelScope artifact linked | Community GGUF, 4.68 GB | Official README declares Apache-2.0; no standalone file | Convert official weights, then publish with Apache notice |
| `xuanyuan-6b-chat` | HF and ModelScope `Duxiaoman-DI/XuanYuan-6B-Chat` | Community GGUF, 3.86 GB | `license: llama2` metadata; no standalone file | Guided official download/import only |

Repository and license findings:

- The authoritative DianJin project is
  [`aliyun/qwen-dianjin`](https://github.com/aliyun/qwen-dianjin). Its official
  release table links
  [`DianJin/DianJin-R1-7B`](https://huggingface.co/DianJin/DianJin-R1-7B)
  and
  [`tongyi_dianjin/DianJin-R1-7B`](https://modelscope.cn/models/tongyi_dianjin/DianJin-R1-7B).
  The Hugging Face model card declares MIT but does not ship a separate
  LICENSE file. A community `Q4_K_M` conversion exists at
  [`mradermacher/DianJin-R1-7B-GGUF`](https://huggingface.co/mradermacher/DianJin-R1-7B-GGUF)
  (4,683,073,824 bytes). StockPulse should convert the pinned official weights
  itself rather than republish that third-party artifact.
- [`SUFE-AIFLM-Lab/Fin-R1`](https://github.com/SUFE-AIFLM-Lab/Fin-R1) is the
  runnable 7B release. Fin-R1-Pro is an official 32B successor, not a 7B
  artifact, so it does not replace this catalog selection. The Fin-R1 README
  explicitly links Apache-2.0 but the repository and HF snapshot contain no
  standalone LICENSE file. A community `Q4_K_M` conversion exists at
  [`mradermacher/Fin-R1-GGUF`](https://huggingface.co/mradermacher/Fin-R1-GGUF)
  (4,683,073,760 bytes). StockPulse-hosted output must be produced from the
  official snapshot and include the Apache license and attribution.
- The official
  [`Duxiaoman-DI/XuanYuan`](https://github.com/Duxiaoman-DI/XuanYuan)
  release table links the exact 6B Chat repositories on
  [Hugging Face](https://huggingface.co/Duxiaoman-DI/XuanYuan-6B-Chat) and
  [ModelScope](https://modelscope.cn/models/Duxiaoman-DI/XuanYuan-6B-Chat/summary).
  Both the upstream card and community GGUF metadata say `license: llama2`, but
  neither the model repository nor the source repository contains the full
  license grant. Because that evidence does not establish a clean project
  redistribution package, StockPulse must not host its weights. The catalog
  links the official source for user-directed download and local import. The
  community `Q4_K_M` evidence is
  [`mradermacher/XuanYuan-6B-Chat-GGUF`](https://huggingface.co/mradermacher/XuanYuan-6B-Chat-GGUF)
  (3,863,640,192 bytes).

License conclusions here govern StockPulse distribution only and are not legal
advice. Model users must review the current upstream terms for their use case.

## Distribution Recommendation

Use an owned Ollama namespace for redistributable finance models after a
separate release task reproduces and validates the conversion. The catalog
reserves `stockpulse/dianjin-r1-7b:q4_k_m` and
`stockpulse/fin-r1-7b:q4_k_m`, but marks both `conversion_required`; these are
not pullable releases today.

The publishing runbook is:

1. Pin the official upstream revision recorded in the catalog and verify every
   downloaded file checksum.
2. Convert and quantize in a reproducible environment, then run prompt-format,
   load, generation, and StockPulse analysis smoke tests.
3. Bundle the applicable license text, upstream attribution, source revision,
   conversion command, quantizer revision, GGUF checksum, and Modelfile.
4. Use an organization-owned Ollama account/namespace, run `ollama signin`,
   create the namespaced model, and `ollama push <namespace>/<model>:<tag>`.
   Publishing credentials or Ollama identity material must live in protected
   release secrets, never in the repository or build logs.
5. Only after the remote digest is independently pulled and verified should a
   follow-up change set `hosted_by_stockpulse=true`, `status=available`, and an
   actual `ollama_tag` in the catalog.

GitHub Release model packs are the fallback, not the primary path. Multi-GB
GGUF files add asset-size, resume, checksum, disk-space, and local-import
complexity that the existing Ollama pull lifecycle already solves. That path
would require a GitHub release token with repository contents permission,
signed checksums, deterministic archive/chunk assembly, partial-download
cleanup, and a completed model-pack importer. Never publish XuanYuan weights
through either path until its redistribution grant is clarified.

## Reproducible GGUF Conversion

Use a pinned [`llama.cpp`](https://github.com/ggml-org/llama.cpp) revision, not
an unversioned local checkout. The high-level process for an allowed model is:

```bash
python3 convert_hf_to_gguf.py /path/to/official-model \
  --outfile model-f16.gguf --outtype f16
./build/bin/llama-quantize model-f16.gguf model-Q4_K_M.gguf Q4_K_M
```

Start with a minimal Modelfile so the GGUF's converted tokenizer/chat-template
metadata remains authoritative:

```dockerfile
FROM ./model-Q4_K_M.gguf
PARAMETER num_ctx 8192
```

XuanYuan 6B was trained with a 2048-token context and an upstream dialogue
format that omits a system message. If a user imports it locally, begin with
`PARAMETER num_ctx 2048` and validate the exact Human/Assistant template from
the official model card. Do not publish any finance package until a golden
prompt proves its chat template and stop tokens.

## StockPulse Configuration

After `ollama pull qwen3:8b`, a channel-mode configuration can use:

```env
LLM_CONFIG_MODE=channels
LLM_CHANNELS=ollama
LLM_OLLAMA_PROVIDER=ollama
LLM_OLLAMA_BASE_URL=http://localhost:11434
LLM_OLLAMA_MODELS=qwen3:8b
LITELLM_MODEL=ollama/qwen3:8b
AGENT_LITELLM_MODEL=ollama/qwen3:8b
```

`AGENT_LITELLM_MODEL` is optional; leave it empty to inherit the primary model.
When the Web settings page writes task assignments, it uses the canonical
connection-aware ModelRef rather than a hand-authored ambiguous route. Configure
ordered fallback behavior through **Settings > AI & Models > Reliability** and
declare every backing connection in `LLM_CHANNELS`; do not copy unverified
environment variables from third-party setup guides.

**Settings > AI & Models > Local Models** is the sole download and management
surface. Web uses the backend's server-configured Ollama proxy, while Desktop
uses lifecycle IPC from the same panel. A successful pull registers the model
through `SystemConfigService` and selects it as primary only when no primary
exists; primary and Agent assignment remain explicit independent actions.
Guided-only finance entries never expose a pull action. Active primary or Agent
models cannot be deleted. The first-run Local Model path embeds the same panel
and proceeds to the Analysis Workbench after activation.

The catalog API is:

```text
GET /api/v1/system/config/llm/local-models
```

Runtime status, background pull submission/polling, assignment, and deletion
are exposed under `/api/v1/local-models`. The proxy always obtains its Ollama
base URL from server configuration. Desktop completion requests carry the
configuration version and a SHA-256 identity of the observed normalized runtime;
they never carry a target URL. The backend recomputes that identity from its own
configuration and rejects activation or unregistration when either snapshot
value changed during the operation. While a Desktop deletion recovery is
pending, the backend reserves that model against concurrent local-model pulls
or registration. Every lifecycle registration remains catalog-backed. Recovery
is single-use and bound to the exact post-unregister configuration and runtime
identity; it optimistically restores that snapshot offline without probing a
stopped or temporarily unavailable runtime. Successful weight deletion retries
idempotent recovery revocation once. If acknowledgement remains unavailable,
deletion still succeeds and any unrevoked token expires after its short TTL.

Run `python scripts/check_local_model_catalog.py` after every catalog or desktop
packaging change.

## Quality Verification Status

No finance-vs-Qwen StockPulse pipeline comparison is claimed by this catalog
change. The development machine had only `qwen3:4b` installed, while neither
redistributable finance selection had a project-owned, checksum-approved
Ollama artifact. Downloading an unreviewed community conversion solely to
produce a result would bypass the provenance boundary above. A later publishing
task must record reproducible A-share, Hong Kong, and U.S. stock samples before
making comparative quality claims.
