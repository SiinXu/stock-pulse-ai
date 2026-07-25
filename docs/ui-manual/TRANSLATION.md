# UI manual translation notes

## File naming

| Language | Pattern |
| --- | --- |
| Simplified Chinese (source) | `NN-topic.md`, `README.md` |
| English | `NN-topic_EN.md`, `README_EN.md` |

Keep the same numeric prefix and topic slug across languages so indexes stay aligned.

## Product UI languages vs manual languages

| Layer | Languages | Source of truth |
| --- | --- | --- |
| **Product UI strings** | `zh`, `en`, plus additional locales (e.g. `zh-TW`, `ja`, `ko`, `de`, `es`, `fr`, `id`, `ms`) | `apps/dsa-web/src/i18n/` (`uiText.ts`, `translations/*`) |
| **This operation manual** | Simplified Chinese + English | `docs/ui-manual/*` |

- Switching the in-app UI language does **not** auto-switch this documentation folder.
- When documenting a control, prefer the **live UI label** for the language the chapter is written in; if labels drift, fix the manual in a docs PR rather than inventing parallel names.
- Adding a full manual in another language (e.g. `_CHT.md` / `_JA.md`) is optional and must keep **identical module boundaries**.

## Scope rules

- Translate **user-facing UI procedures** only.
- Do not expand into deployment, secrets, or server runbooks in this folder.
- Prefer product terms already used in Web copy. For financial wording, follow [financial-terminology-guide.md](../financial-terminology-guide.md) and [web-i18n.md](../web-i18n.md).
- Keep the research-only disclaimer in every language.
- Each module chapter should include, in both languages:
  - **Entry paths** (nav + route + important query params)
  - **Glossary** for page-specific terms
  - **Step-by-step operations**
  - **Use cases**
  - **Links** to adjacent modules

## When UI labels or routes change (PR checklist)

Any PR that changes Web/Desktop IA, routes, tab names, or settings sections should:

1. Diff against `apps/dsa-web/src/routing/routes.ts` and `components/layout/navigation.ts`.
2. Update the affected `docs/ui-manual/NN-*.md` **and** `*_EN.md` pairs.
3. Update nav tables in `01-shell` / `README` if top-level IA changed.
4. Note temporary mismatches in the PR body if a follow-up docs PR is required.

## When UI labels differ from the manual

If the live UI string differs from the manual, prefer the **live UI** and update the manual in a follow-up docs PR. Document temporary mismatches in the PR description rather than inventing parallel product names.

## Screenshots / figure pack

- Storage: `docs/ui-manual/assets/`
- Naming, captions, refresh triggers, and the P0/P1 starter set: [assets/README.md](assets/README.md)
- Do not commit one-off issue/PR review screenshots under random paths; use the pack naming and bilingual captions.
- Related tracking: issue #599

## Adding a language

1. Copy each `*_EN.md` (or Chinese source) to a new suffix agreed by maintainers (for example `_CHT.md`).
2. Add links in `README.md` / `README_EN.md` and in `docs/INDEX.md` / `docs/INDEX_EN.md`.
3. Keep module boundaries identical; do not merge or split modules per language.
4. Run a quick pass that every cross-link target exists for the new suffix.
