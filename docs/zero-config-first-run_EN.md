# Zero-config first success

Issue: [#796](https://github.com/SiinXu/stock-pulse-ai/issues/796)

Chinese: [zero-config-first-run.md](zero-config-first-run.md)

## Acceptance meaning

1. Fresh install with **no** `.env` secrets and **no** primary model API key.
2. Start the app → see first-run guidance.
3. Reach **one** analysis-shaped result without filling required cloud fields:
   - Prefer **local Ollama** when loopback detect succeeds (official `local-first` preset fields only).
   - Otherwise open the **offline sample analysis** (always labeled sample data).
4. Existing users who already have a primary model or prior setup are **not** force-switched to beginner defaults, and readiness never mutates their config.

## APIs

| Method | Path | Mutates config? | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/onboarding/first-run` | No | Fresh-env signal, beginner recommendation, local detect snapshot, primary CTA |
| `GET` | `/api/v1/onboarding/demo-analysis?report_language=zh\|en` | No | Offline fixture; always `is_sample=true` |
| `POST` | `/api/v1/onboarding/apply` | Yes (explicit confirm) | Reuse to apply `infrastructure=local_models` → `local-first` preset |

Local detect reuses `src/services/local_runtime_detect.py`. Presets are read from `src/services/config_presets.py` (not reimplemented).

## UI

- Self-contained component: `apps/dsa-web/src/components/onboarding/ZeroConfigFirstRunPanel.tsx`
- Playground: `zero-config-first-run-panel`
- Home / Settings wiring is an **Integration Point** (host pages frozen in this parallel batch).

## Related

- Official presets: issue #795 / `config_presets.py`
- Backend detect wave: PR #817
- Beginner install guide: [beginner-client-setup_EN.md](beginner-client-setup_EN.md)
