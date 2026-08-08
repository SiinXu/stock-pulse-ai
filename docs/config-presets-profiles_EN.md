# Recommended Config Presets & stockpulse-profile YAML

This guide covers official **recommended configuration presets** and the versioned **stockpulse-profile** YAML format (issue #795).

## Goals

- One-click (confirm-first) apply of coherent, tested non-secret configuration.
- Portable import/export of reviewable config packs **without secrets**.
- Local-first bias: recommend Ollama / Model Pack / CLI when healthy.
- Agent-ready structure for future guided onboarding (#589).

## Official presets

| ID | Display | Recommendation bias |
| --- | --- | --- |
| `local-first` | Local-first (Ollama / Model Pack) | Ollama healthy or Model Pack present |
| `cli-backends` | CLI backends | Detected `codex` / `claude` / `opencode` CLI |
| `cloud-balanced` | Cloud balanced | Cloud credentials present; default when nothing local is detected |
| `power-user` | Custom / advanced | Explicit advanced path; minimal forced keys |

Presets are pure data under `src/services/config_presets.py` and are applied **only** through `SystemConfigService` (no parallel write path).

## stockpulse-profile YAML v1

```yaml
apiVersion: stockpulse/v1
kind: Profile
metadata:
  name: local-first-ollama
  displayName: Local-first (Ollama)
  description: Prefer local models; never embeds secrets
  version: "1.0.0"
  tags: [local, privacy]
spec:
  llm:
    preferenceOrder: [ollama, model_pack, cli, cloud]
    config:
      GENERATION_BACKEND: litellm
      LLM_CONFIG_MODE: channels
      # channel / model ids only — never secrets
  strategies:
    enabled: [bull_trend]
  features:
    beginnerMode: true
  requirements:
    minRamGb: 16
    needsOllama: true
```

Example files live under `docs/examples/profiles/`.

### Security rule (mandatory)

**Profiles NEVER export secret values.**

- Export excludes keys matching secret markers (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `*_EXTRA_HEADERS`, and `LITELLM_CONFIG`).
- Import **rejects** any secret-shaped key with `config_profile_secret_rejected`.
- Apply paths never invent API keys.
- This rule is encoded in service code, API contracts, automated tests, and this document.

## API

Base path: `/api/v1/config-profiles`

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/presets` | List presets + local-first ranking |
| `POST` | `/presets/{id}/preview` | Diff before apply |
| `POST` | `/presets/{id}/apply` | Apply non-secret keys via SystemConfigService |
| `GET` | `/export` | Export secret-stripped YAML |
| `POST` | `/import/preview` | Validate + preview import |
| `POST` | `/import/apply` | Apply imported profile |

Apply/import bodies require the current `config_version` (same optimistic concurrency model as system config).

## Web UI

Settings → **Advanced** → **Config Backup** hosts the **Recommended presets & profiles** panel:

1. Recommended preset is badged from runtime detection.
2. Apply always shows a change summary confirm dialog.
3. Export downloads YAML; import previews a diff before writing.

## Related docs

- [LLM Configuration Guide (EN)](./LLM_CONFIG_GUIDE_EN.md)
- [Beginner client setup (EN)](./beginner-client-setup_EN.md)
- [Model Packs](./model-packs.md)
