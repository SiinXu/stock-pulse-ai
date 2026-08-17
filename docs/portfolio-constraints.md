# 组合研究提案约束引擎

对应 Issue [#1132](https://github.com/SiinXu/stock-pulse-ai/issues/1132) 的后端 V1。

研究侧提出的操作 / 再平衡情景在被标为「约束可行」之前，会经过**确定性规则引擎**。引擎**不会**下单、改写账本，也**不能**替代券商、交易所或监管合规。

**仅供研究参考，不构成投资建议，也不是券商合规。**

完整字段、配置形状与接线说明见英文文档：[portfolio-constraints_EN.md](portfolio-constraints_EN.md)。

## 检查范围

- 单票上限（per-name cap）
- 行业上限（sector cap）
- 黑名单（blacklist）
- 简单风险标记（simple risk flags）

数值比较只在 `src/services/portfolio/constraints.py` 中完成，禁止交给 LLM 做算术。

## 结论标签

- `constraint_feasible`：已配置的**研究约束**未阻断提案。这不是下单许可。
- `research_only`：提案违规或引擎无法安全评估，不得当作可执行情景。
- `executable` / `auto_execute` 始终为 `false`；`not_broker_compliance` 始终为 `true`。

`PortfolioAgent.post_process` 会调用同一条真实接线：`apply_constraints_to_research_assessment`。

## 回滚

还原实现 PR 即可；无数据库迁移。
