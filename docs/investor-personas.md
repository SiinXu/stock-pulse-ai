# 投资者 Persona 与研究立场

[中文](investor-personas.md) | [English](investor-personas_EN.md)

对应 Issue [#119](https://github.com/SiinXu/stock-pulse-ai/issues/119) 与 [#467](https://github.com/SiinXu/stock-pulse-ai/issues/467)。

Persona 为**结构化数据**，建立在：

1. **投资视角** — `strategies/personas/` Skill YAML
2. **研究立场** — 配置 / 请求 / 个人投资框架 `research_stance`

默认**关闭**。人物名仅作风格参考。

## 启用

- 视角：`AGENT_SKILLS` / 投资委员会 / 请求 `personas`
- 立场：`AGENT_RESEARCH_PERSONA` / 框架 `research_stance` / 请求 `research_persona`

启用后在分析/Agent 提示词注入，并在 `dashboard.active_research_persona` 标注。

## 合规

仅供学习研究；非关联/背书；非投资建议。

## 相关

- [个人投资框架](personal-investment-framework.md)
- [投资委员会模式](investment-committee-mode.md)
