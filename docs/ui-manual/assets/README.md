# UI manual figure pack

Annotated screenshots (or language-neutral chrome crops) for the operation manual live here when maintainers add them.

This directory implements the storage side of issue **#599** (annotated screenshot / figure pack). Until images exist, chapters remain text + mermaid first.

## Goals

- Help zero-basis users answer “where is the button?”
- Stay in sync with product IA and i18n without committing one-off PR review screenshots into random paths
- Prefer **one pack per major release** over ad-hoc images in every docs PR

## Naming convention

```
docs/ui-manual/assets/
  <module>-<scene>[-<lang>].<ext>
```

| Part | Rules | Examples |
| --- | --- | --- |
| `module` | Manual module slug without number, lowercase kebab | `home`, `shell`, `analysis-workbench`, `signals`, `settings`, `discover` |
| `scene` | Short scene id, kebab-case | `config-gap`, `three-segments`, `task-running`, `report-header`, `tabs-empty`, `save-control` |
| `lang` | Optional. Omit when chrome is language-neutral or bilingual in product | `zh`, `en` |
| `ext` | `png` or `webp` preferred | `home-config-gap-zh.png` |

Examples:

| File | Meaning |
| --- | --- |
| `home-config-gap-zh.png` | Home setup-incomplete banner (Simplified Chinese UI) |
| `analysis-workbench-three-segments-en.png` | Workbench launch / tasks / history segments (English UI) |
| `signals-tabs-empty.png` | Signal Center tabs + empty feed (shared chrome) |
| `settings-save-control-zh.png` | Settings save control location |
| `report-header-action-phase.png` | Report header: action + phase + data-quality affordance |

## Required starter set (priority)

| Priority | Scene | Suggested filename stem | Used by chapter |
| --- | --- | --- | --- |
| P0 | Home configuration gap + primary CTA | `home-config-gap` | [02](../02-home.md) |
| P0 | Analysis Workbench three segments | `analysis-workbench-three-segments` | [03](../03-analysis-workbench.md) |
| P0 | Running task progress states | `analysis-workbench-task-running` | [03](../03-analysis-workbench.md) |
| P0 | Report header: action, phase, quality | `report-header-action-phase` | [08](../08-reading-reports.md) |
| P1 | Signal Center tabs + empty state | `signals-tabs-empty` | [06](../06-signals.md) |
| P1 | Settings save control | `settings-save-control` | [10](../10-settings.md) |

## Caption and alt text rules

1. Every figure in a manual chapter needs:
   - Markdown image with meaningful **alt text** (describe the UI region, not “screenshot”).
   - A one-line **caption** under the image in the chapter language.
2. Captions must use **live product labels** for that language. Do not invent parallel names.
3. If zh and en UI differ only by strings, prefer two crops (`-zh` / `-en`) or one neutral chrome crop plus caption text in each language chapter.
4. Do not embed secrets, API keys, personal portfolio sizes, or real account identifiers. Use demo symbols (`600519`, `AAPL`) and redaction.

## When to refresh figures

Refresh the pack (or the affected stems) when any of these ship:

- Primary nav / Research children change
- Signal Center tab rename or route change
- Report header layout change (action / phase / quality)
- Settings save control or section IA change
- Home core blocks restructure

Link the refresh to the product PR or a dedicated docs PR; mention the stem list in the PR body.

## How to embed in a chapter

```markdown
![Home: basic configuration incomplete banner and Start guided setup button](assets/home-config-gap-zh.png)

*Caption: Home warning when readiness checks fail — use **Start guided setup**.*
```

English chapters point at `-en` or language-neutral files:

```markdown
![Home: setup incomplete banner and Start guided setup](assets/home-config-gap-en.png)

*Caption: Home warning when readiness checks fail — use **Start guided setup**.*
```

## What not to commit here

- Issue/PR review screenshots tied to a single ticket number as the only filename context
- Marketing hero art
- Full video tours (link externally if needed)
- Unredacted production data

## Status

| Item | Status |
| --- | --- |
| Naming + location documented | Done (this file + [TRANSLATION.md](../TRANSLATION.md)) |
| Full scene list + capture brief | Done — [PLACEHOLDERS.md](PLACEHOLDERS.md) |
| P0/P1 binary assets | **Pending** maintainer capture against live UI |
| Chapter embeds | **Placeholder blocks in** modules 01–13 (no broken image links until files exist) |

### Placeholder convention in chapters

Until a PNG/WebP exists, chapters use a blockquote—not `![](…)`—so GitBook/Honkit never show a broken image:

```markdown
> 🖼️ **配图占位** · `assets/<stem>-zh.png`
> **应配内容**：……
> **拍摄要点**：……
> **状态**：待补图（清单：assets/PLACEHOLDERS.md）
```

When the file is ready: replace the blockquote with a real image + one-line caption (see rules above), and tick the stem in [PLACEHOLDERS.md](PLACEHOLDERS.md).
