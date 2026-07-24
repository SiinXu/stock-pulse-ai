# UI manual translation notes

## File naming

| Language | Pattern |
| --- | --- |
| Simplified Chinese (source) | `NN-topic.md`, `README.md` |
| English | `NN-topic_EN.md`, `README_EN.md` |

Keep the same numeric prefix and topic slug across languages so indexes stay aligned.

## Scope rules

- Translate **user-facing UI procedures** only.
- Do not expand into deployment, secrets, or server runbooks in this folder.
- Prefer product terms already used in Web copy. For financial wording, follow [financial-terminology-guide.md](../financial-terminology-guide.md) and [web-i18n.md](../web-i18n.md).
- Keep the research-only disclaimer in every language.

## When UI labels differ

If the live UI string differs from the manual, prefer the **live UI** and update the manual in a follow-up docs PR. Document temporary mismatches in the PR description rather than inventing parallel product names.

## Adding a language

1. Copy each `*_EN.md` (or Chinese source) to a new suffix agreed by maintainers (for example `_CHT.md`).
2. Add links in `README.md` / `README_EN.md` and in `docs/INDEX.md` / `docs/INDEX_EN.md`.
3. Keep module boundaries identical; do not merge or split modules per language.
