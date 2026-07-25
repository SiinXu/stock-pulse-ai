# StockPulse Model Packs

StockPulse Model Packs are versioned, data-only bundles for importing a local
GGUF model into Ollama. They support offline transfer and models whose license
does not permit StockPulse to redistribute weights through an Ollama registry.

A Model Pack never contains or runs an installer, conversion program, plugin,
shell command, or other executable content. Import validates every declared
payload before calling Ollama.

## User Import

Use `Settings -> AI -> Local Models -> Import Model Pack`. This is the only
supported model-import entry point.

- Desktop accepts a `.modelpack`/`.zip` file or an unpacked Model Pack
  directory. The native picker asks which source type to select.
- Web accepts a `.modelpack` or `.zip` upload. The server stages the upload and
  removes the staging directory when the background task ends. Uploads,
  archives, and declared payloads are limited to 64 GiB. Before Starlette can
  parse or spool the multipart file, ASGI ingress enforces `Content-Length` and
  counts chunked request bytes. The complete multipart envelope is limited to
  64 GiB plus 1 MiB of bounded form overhead; the file itself remains limited
  to exactly 64 GiB.
- Once the server accepts a Web import, the panel observes the server-owned task
  until it reaches a terminal state. Closing the panel or cancelling the
  browser request may stop observation, but the client does not invent a
  timeout while the accepted background task is still running.
- The Web request cannot provide an Ollama URL. StockPulse reads
  `LLM_OLLAMA_BASE_URL` from saved server configuration.
- A private or loopback Web Ollama target must also be allowed by the existing
  outbound policy, for example
  `OUTBOUND_HTTP_ALLOWLIST=127.0.0.1:11434`.
- Desktop uses the currently resolved trusted Ollama executable: a working
  system installation takes precedence, with the bundled runtime as fallback.
  It calls `ollama create` with a fixed argument array and `shell=false`. Pack
  content is never added to a command line except for the validated model id
  and a StockPulse-owned canonical Modelfile path generated from the validated
  projection.
- Desktop returns validated manifest metadata, an opaque runtime identity, and
  a short-lived one-time attestation to the Web panel. The attestation binds
  the exact validated fields to an ephemeral secret shared only by Electron
  main and its managed backend; an ordinary API caller cannot register
  unvalidated metadata. The backend consumes it and checks the original
  configuration/runtime snapshot before using the same activation path as a
  catalog download.

After successful creation, StockPulse adds `ollama` to `LLM_CHANNELS`, adds the
model id to `LLM_OLLAMA_MODELS`, enables that channel, and reloads configuration
through the same path used by Local Model downloads. An existing primary model
is not replaced. If no primary model exists, the Local Models activation flow
may select the imported Ollama route so the first analysis can run without
manual environment editing.

Validated presentation metadata for imported models that are absent from the
catalog is stored in `model_pack_registry.json` beside `DATABASE_PATH`. The
bounded JSON registry is written atomically with owner-only file permissions
and keyed by an opaque Ollama runtime identity. A catalog match always uses
catalog presentation; manifest presentation is shown only for unknown models.

The import needs working space for validation/extraction and for Ollama's model
store. Archive imports first copy the opened archive into bounded private
storage so pathname replacement cannot change the bytes between inventory and
extraction. StockPulse checks free space before that snapshot and again before
extraction, but Ollama may use a different disk. A later Ollama disk failure is
therefore still possible.

### Failure Guidance

| Error | Meaning | Action |
| --- | --- | --- |
| `unsupported_format_version` | The pack targets a newer format | Update StockPulse or obtain a v1 pack |
| `missing_manifest` / `missing_file` | Required data is absent | Download or build the complete pack again |
| `size_mismatch` / `hash_mismatch` | Payload integrity does not match the manifest | Do not use the pack; re-download it from the trusted source |
| `unsafe_archive_entry` | The archive contains a nested, duplicate, traversal, or symbolic-link entry | Rebuild it with `scripts/build_model_pack.py` |
| `unsafe_modelfile` | Modelfile exceeds 1 MiB, references an external path, or uses an unsupported instruction | Reduce or correct the Modelfile and rebuild |
| `invalid_license_file` | The license exceeds 2 MiB or is not valid UTF-8 text | Use the complete bounded UTF-8 license text and rebuild |
| `invalid_gguf` | The declared weight does not have the GGUF header | Select the correct converted weight |
| `model_pack_too_large` | The upload, archive, or declared payload exceeds 64 GiB | Select or build a smaller pack |
| `invalid_archive` | The archive is unreadable or contains more than 256 files | Re-download it or rebuild it with only declared data |
| `insufficient_disk_space` | Staging/import free space is below the preflight requirement | Free the amount shown and retry |
| `ollama_access_blocked` | The configured private target is not allowed by outbound policy | Add the exact trusted host and port to `OUTBOUND_HTTP_ALLOWLIST` |
| `ollama_unavailable` | Ollama cannot be reached or started | Start Ollama and verify `LLM_OLLAMA_BASE_URL` |
| `ollama_create_failed` | Ollama rejected or could not finish model creation | Check Ollama compatibility/logs, then rebuild or retry |
| `registration_failed` | Ollama created the model but StockPulse could not activate it | Open Local Models and register the installed model |
| `config_version_conflict` | Configuration or runtime changed during Desktop import | Refresh Local Models and retry the activation |

## Format Version 1

A v1 directory and its archive representation contain these root-level files:

```text
manifest.json
<one-model>.gguf
Modelfile
LICENSE
```

File names may contain ASCII letters, digits, `.`, `_`, and `-`; they cannot
end in `.`, and Win32 device basenames such as `CON`, `NUL`, `COM1`, and `LPT1`
are reserved. Paths,
subdirectories, and symbolic links are not valid declared payloads. A release
archive uses ZIP container semantics and normally uses the `.modelpack`
extension. `.zip` is also accepted.

`manifest.json` is the only metadata entry point. It lists exactly one `gguf`,
one `modelfile`, and one `license` payload. Every listed file has a byte size
and lowercase SHA-256 digest. `manifest.json` does not hash itself; the builder
creates a sidecar checksum for the complete archive.

```json
{
  "display_name": "Example Finance 7B Q4",
  "files": [
    {
      "path": "example-finance-q4.gguf",
      "role": "gguf",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "size_bytes": 4200000000
    },
    {
      "path": "Modelfile",
      "role": "modelfile",
      "sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
      "size_bytes": 132
    },
    {
      "path": "LICENSE",
      "role": "license",
      "sha256": "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0",
      "size_bytes": 11358
    }
  ],
  "format_version": 1,
  "gguf_file": "example-finance-q4.gguf",
  "license": {
    "file": "LICENSE",
    "id": "Apache-2.0"
  },
  "minimum_memory_gb": 16,
  "model_id": "stockpulse/example-finance:q4",
  "modelfile": "Modelfile"
}
```

Field rules:

| Field | Contract |
| --- | --- |
| `format_version` | Integer `1` |
| `model_id` | Explicit ASCII `model:tag` or `namespace/model:tag`; each component is 1-80 characters. Namespace starts with an alphanumeric or `_` and then uses alphanumerics, `_`, or `-`; model and tag additionally allow `.` after the first character |
| `display_name` | Non-empty user-visible name, at most 160 Unicode scalar values |
| `gguf_file` | Root-level `.gguf` filename matching role `gguf` |
| `modelfile` | Root-level filename matching role `modelfile` |
| `license.id` | SPDX identifier or `LicenseRef-*` identifier |
| `license.file` | Root-level UTF-8 text file matching role `license` |
| `minimum_memory_gb` | Positive integer GiB tier |
| `files` | Exactly three unique entries with unique roles, byte sizes, and SHA-256 digests |

Extra regular files produce warnings and are not extracted from an archive.
Missing declared files fail import. Unsafe archive names, duplicate
case-insensitive names, nested paths, and symbolic links fail import even when
they are not declared. Every archive member name uses the same portable ASCII
filename alphabet as a declared payload. Directory and archive inventories are capped at 256
entries (including empty directories), and the archive plus the sum of
declared payload sizes are each capped at 64 GiB. `manifest.json` and the
constrained Modelfile are each capped at 1 MiB; the UTF-8 license payload is
capped at 2 MiB.

### Constrained Modelfile

The only accepted instructions are:

- `FROM`: exactly once and only `./<gguf_file>` or `<gguf_file>`;
- `PARAMETER`: one supported lowercase Ollama option with its declared value
  type; each name appears once except `stop`, which may repeat and becomes an
  ordered string list;
- `TEMPLATE`: once, either unquoted one-line text or a triple-quoted block;
- `SYSTEM`: once, either unquoted one-line text or a triple-quoted block.

All other instructions are rejected, including `ADAPTER`, `LICENSE`, and
`MESSAGE`. In particular, `FROM` cannot name an absolute path, parent path,
registry model, URL, or file outside the pack. Single-line `TEMPLATE` and
`SYSTEM` values with outer quotes, and repeated scalar parameters other than
`stop`, are rejected so Web native-create and Desktop Modelfile parsing cannot
interpret one valid pack differently.

The portable grammar uses UTF-8 without a byte-order mark, LF or CRLF line
endings, ASCII instruction/parameter names, and ASCII space (`U+0020`) for
indentation and instruction/value separation. Tabs, bare carriage returns,
Unicode line separators, and byte-order marks are rejected. Text may contain
Unicode letters, marks, numbers, punctuation, symbols, ASCII spaces, and block
newlines; format characters and other runes that Ollama would silently discard
are rejected.

Supported parameters and types are:

| Type | Parameters | Accepted form |
| --- | --- | --- |
| Integer | `num_ctx`, `num_batch`, `num_gpu`, `main_gpu`, `num_thread`, `draft_num_predict`, `num_keep`, `seed`, `num_predict`, `top_k`, `repeat_last_n` | Canonical base-10 integer within `-(2^53-1)` through `2^53-1` |
| Float | `top_p`, `min_p`, `typical_p`, `temperature`, `repeat_penalty`, `presence_penalty`, `frequency_penalty` | Finite JSON number that neither overflows nor underflows Ollama's 32-bit float; normalized to that portable value |
| Boolean | `use_mmap` | Lowercase `true` or `false` |
| String list | `stop` | Double-quoted text; may repeat |

Unknown, differently cased, or type-mismatched parameters are rejected.
Double quotes around `stop` values are delimiters only: backslash sequences are
preserved literally to match Ollama's parser, while inner double quotes are
rejected as ambiguous. `null`, containers, and non-finite numbers are rejected.

```text
FROM ./example-finance-q4.gguf
PARAMETER temperature 0.2
PARAMETER num_ctx 8192
SYSTEM """You are a financial research model.
Distinguish reported facts from inference."""
```

The Web path translates the validated fields to Ollama's native blob and
`/api/create` APIs. The Desktop path gives `ollama create` a canonical LF
Modelfile generated from that same validated projection. This preserves
delimiter-only triple-block leading newlines, CRLF-authored content, parameter
names, and parameter types consistently across both transports. Non-ASCII
boundary whitespace is rejected because Ollama would silently discard it. The
separately validated license remains Model Pack distribution
and StockPulse registry metadata; neither transport adds it as an Ollama
license layer. See the official
[Ollama create API](https://docs.ollama.com/api/create) for the downstream
runtime contract.

Cancellation is checked after validation, before any Web blob work, and again
after a blob check or upload before StockPulse issues the irreversible
`/api/create` request. If cancellation arrives while that request is already in
flight, StockPulse prevents activation and registration, but Ollama may retain
the model created by the request.

## Publisher Workflow

Do not redistribute a model until its license and upstream terms have been
reviewed for the exact weight and conversion. A catalog entry marked as guided
download is not permission to host its weights.

Prepare these files in one directory:

1. the final GGUF weight;
2. a constrained `Modelfile` whose `FROM` matches that GGUF basename;
3. the complete UTF-8 license text.

Build the package:

```bash
python3 scripts/build_model_pack.py \
  --gguf ./release-input/example-finance-q4.gguf \
  --modelfile ./release-input/Modelfile \
  --license-file ./release-input/LICENSE \
  --model-id stockpulse/example-finance:q4 \
  --display-name "Example Finance 7B Q4" \
  --license-id Apache-2.0 \
  --minimum-memory-gb 16 \
  --output ./dist/model-packs/example-finance-q4-v1.modelpack
```

The builder:

- validates GGUF magic, the 1 MiB Modelfile limit and subset, and the 2 MiB
  UTF-8 license limit;
- computes each payload SHA-256 and byte size;
- writes canonical `manifest.json`;
- stores the already-compressed GGUF without recompressing it;
- writes stable ZIP order, timestamp, and permissions;
- publishes the archive and whole-artifact checksum through same-directory
  atomic replacements, restoring the prior pair if ordinary publication fails; and
- creates `example-finance-q4-v1.modelpack.sha256` for the entire artifact.

Verify from a clean directory before publishing:

```bash
(cd ./dist/model-packs && \
  shasum -a 256 -c example-finance-q4-v1.modelpack.sha256)
python3 - <<'PY'
from pathlib import Path

from src.model_pack import inspect_model_pack

with inspect_model_pack(
    Path("./dist/model-packs/example-finance-q4-v1.modelpack")
) as pack:
    print(pack.manifest.model_id)
PY
```

Name release assets as `<model-slug>-<quantization>-v<format>.modelpack` plus
the matching `.sha256`. Record upstream repository/revision, conversion tool
revision and command, quantization, license conclusion, source digest, output
digest, and minimum-memory evidence in the release notes.

For an eligible artifact:

```bash
gh release upload <tag> \
  ./dist/model-packs/example-finance-q4-v1.modelpack \
  ./dist/model-packs/example-finance-q4-v1.modelpack.sha256
```

GitHub documents that each Release asset must be
[under 2 GiB](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas).
Most 7B and larger Q4 GGUF packages exceed that limit. Format v1 is a
single-archive format and must not be renamed or manually split into
undeclared pieces. For a larger redistributable model, use a license-approved
external object store with the same archive/checksum, or publish instructions
for users to build the pack from an authorized source. A future multipart
format requires a new format version and importer contract.

This repository task defines the tooling only. It does not publish weights or
create a Release.

## Configuration And Rollback

Model Pack import adds no user-configurable environment keys. It reuses:

- `LLM_CHANNELS`;
- `LLM_OLLAMA_PROVIDER`;
- `LLM_OLLAMA_PROTOCOL`;
- `LLM_OLLAMA_BASE_URL`;
- `LLM_OLLAMA_MODELS`;
- `LLM_OLLAMA_ENABLED`;
- existing primary/Agent assignment keys when the user explicitly selects
  those roles.

Packaged Desktop launches its managed backend with a random, process-lifetime
attestation key. This internal key is replaced on every Desktop start, is not a
user configuration option, is never written to `.env`, and is not exposed by
the preload bridge.

There is no `LITELLM_FALLBACK_MODELS` setting. Multi-provider fallback remains
the existing ordered `LLM_CHANNELS` behavior and Local Models assignment UI.

To roll back code, revert the Model Pack change. No database migration is
required; the additive `model_pack_registry.json` file can be retained or
removed. A model already created in Ollama remains an ordinary local Ollama
model. Reassign active routes, remove its id from the normal Ollama channel
configuration, and run `ollama rm <model-id>` if the catalog-only deletion
control does not list it. Restore saved configuration through the existing
`.env` backup/import workflow if needed.

The Local Models delete action remains limited to catalog entries that support
the normal direct-pull lifecycle. A planned catalog model installed through a
Model Pack can still be assigned normally, but it does not show that delete
action; use the explicit reassignment and `ollama rm` rollback path above.
