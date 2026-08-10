# Zero-config first success

Issue: [#796](https://github.com/SiinXu/stock-pulse-ai/issues/796)

Chinese: [zero-config-first-run.md](zero-config-first-run.md)

## Acceptance meaning

1. Fresh install with **no** `.env` secrets and **no** primary model API key.
2. Start the app → see first-run guidance.
3. Reach **one** analysis-shaped result without filling required cloud fields:
   - Prefer **local model setup** when loopback Ollama is reachable and has at least one model.
   - When Ollama is reachable with an empty model list, explain the remediation and fall back to the demo path.
   - Otherwise open the **offline sample analysis** (always labeled sample data).
4. Existing users who already have a primary model or prior setup are **not** force-switched to beginner defaults, and readiness never mutates their config.

## APIs

| Method | Path | Mutates config? | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/onboarding/first-run` | No | Fresh-env signal, beginner recommendation, local detect snapshot, primary CTA |
| `GET` | `/api/v1/onboarding/demo-analysis?report_language=zh\|en\|ko` | No | Offline fixture; always `is_sample=true` |

Local detection reuses `src/services/local_runtime_detect.py`; primary-model readiness reuses the authoritative System Settings setup check. `first-run` returns stable reason codes, parameters, and a versioned `snapshot_id`. It does not ship English display copy or expose detect-then-apply semantics.

## UI

- Self-contained component: `apps/dsa-web/src/components/onboarding/ZeroConfigFirstRunPanel.tsx`
- Playground: `zero-config-first-run-panel`
- This PR provides a self-contained foundation; a discoverable Home / Settings product entry remains an **Integration Point**.
- For `configured` / `local_ollama`, the host must provide a settings-navigation handler. Without it, the primary button is disabled with an explanation; it never becomes a silent no-op or substitutes the demo action.

## Related

- Official presets: issue #795 / `config_presets.py`
- Backend detect wave: PR #817
- Beginner install guide: [beginner-client-setup_EN.md](beginner-client-setup_EN.md)
