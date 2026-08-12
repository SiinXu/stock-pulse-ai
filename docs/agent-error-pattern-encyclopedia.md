# 从教训沉淀的错误模式百科

**状态**：Issue [#1138](https://github.com/SiinXu/stock-pulse-ai/issues/1138) 的 V1 库路径

**English**: [agent-error-pattern-encyclopedia_EN.md](agent-error-pattern-encyclopedia_EN.md)

## 在进化栈中的位置

| 层级 | 归属 | 作用 |
| --- | --- | --- |
| 教训（输入） | `#1089` / `#1103` / PR `#1196` | 按 episode / 已解析预测产出的 typed `ReflectionLesson` |
| **百科（聚合层）** | **`#1138`（本文）** | 按模式聚类为人类可编辑卡片；分析时 top-K 清单注入 |
| Soul 宪章 | `src/agent/soul.py` | 不可变；教训与模式都不得改写 |

**教训是输入，百科是聚合层。** 模式卡片引用回具体 episode；不是自由日记，也不是 Soul 编辑。

## 产品规则

1. 将复发教训按 typed kind 聚类为可检索卡片。
2. 人类可编辑 title / description / triggers / remedy，或禁用卡片。
3. 每次人工编辑（含禁用 / 启用 / 改判）**必须追加审计事件**。
4. 分析时只注入 **enabled** 卡片，并受 **top-K** 与 **字符配额** 约束。
5. 注入内容是只读清单，以非权威数据块包装，**不得改变** Agent Soul 宪章字节。
6. 默认关闭（`AGENT_ERROR_PATTERN_ENABLED=false`）。

## 卡片字段

| 字段 | 含义 |
| --- | --- |
| `pattern_id` | 稳定 id（`pattern:<kind>`） |
| `kind` | 共享教训类型 |
| `title` / `description` | 可读文案（有种子默认值，可改判） |
| `triggers` | 常见触发条件 |
| `remedy` | 有界的下次提示（非 Soul 改写） |
| `stats` | 出现次数、严重度计数、`episode_refs` |
| `enabled` | 禁用后分析路径不注入 |
| `revision` | 聚类合并与人工编辑时递增 |
| `human_locked_fields` | 人工改过的字段；再聚类时保留 |

### 模式与产品语言对应

| Kind | 产品语义 |
| --- | --- |
| `evidence_gap` | 数据缺陷 / 证据缺失 |
| `overconfidence` | 过度自信 |
| `horizon_mismatch` | 时机误判 |
| `regime_shift` | 市场阶段 / 体制误判 |
| `tool_failure` | 工具/数据源失败被当成可捏造数据 |
| `risk_omission` | 风险 / 失效条件遗漏 |
| `overclaim` | 叙述被当成可核验断言 |
| `format_violation` | 格式 / Schema 违规 |
| `other` | 有类型的残余桶 |

## 模块

| 模块 | 作用 |
| --- | --- |
| `src/agent/evolution/lessons.py` | 共享教训 taxonomy（输入契约；与 #1196 共用） |
| `src/agent/evolution/error_patterns.py` | 卡片、聚类、存储、人工编辑留痕、检索 |
| `src/agent/evolution/guards.py` | Soul 身份快照 / 断言 |

## 配置

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `AGENT_ERROR_PATTERN_ENABLED` | `false` | 分析注入总开关 |
| `AGENT_ERROR_PATTERN_INJECT_TOP_K` | `3` | 最多注入卡片数（硬顶 3） |
| `AGENT_ERROR_PATTERN_INJECT_CHAR_BUDGET` | `2000` | 清单字符上限（硬顶 8000） |

## 验收映射

| 标准 | 覆盖 |
| --- | --- |
| 卡片可检索 | `retrieve_error_patterns` / `list_cards` |
| 禁用卡片不注入 | `enabled=false` 被分析路径排除 |
| 注入不改 Soul 宪章字节 | Soul 快照 + 宪章字节断言测试 |
| 模式引用 episode | `stats.episode_refs` |
| 人工编辑留痕 | `PatternEditEvent` 追加日志 |
| 配额 | top-K + 字符预算 |

## V1 非目标

- 生产 Orchestrator 自动接线（库路径；默认关）
- 多租户 DB 表 / Web 卡片编辑 UI
- 完整后验 / 反思环（由 #1196 / #1103 / #1089 负责）

## 回滚

将 `AGENT_ERROR_PATTERN_ENABLED=false` 或回退本变更。无 DB 迁移。
