// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { SettingsHelpMap } from './settingsHelpTypes';

const educationHelpZhCN: SettingsHelpMap = {
  'education.risk.level.low': {
    title: '低风险等级',
    summary: '组合风险热力图 0–100 分中低于 25 的相对分档。',
    usage: '当权重、止损距离或回撤压力相对其他持仓仍偏温和时出现。',
    impact: [
      '可视为结构压力较轻的阅读，不等于无风险，也不是买入信号。',
    ],
    notes: [
      '“低”不是零风险；单次市场事件仍可能把任何标的推高到更高等级。',
    ],
  },
  'education.risk.level.medium': {
    title: '中风险等级',
    summary: '0–100 组合风险分中大约 25–49 的中等分档。',
    usage: '当集中度、止损距离或回撤已抬升但尚未极端时出现。',
    impact: [
      '值得再看一眼仓位、止损与分散度，再决定是否继续加风险。',
    ],
  },
  'education.risk.level.high': {
    title: '偏高风险等级',
    summary: '0–100 组合风险分中大约 50–74 的偏高分档。',
    usage: '当结构压力明显强于同视图中更安静的持仓时触发。',
    impact: [
      '优先复核仓位规模与退出计划，再当作日常操作处理。',
    ],
  },
  'education.risk.level.critical': {
    title: '高风险等级',
    summary: '0–100 组合风险分中大约 75–100 的最高分档。',
    usage: '留给热力图中最强的结构压力（权重、止损或回撤）。',
    impact: [
      '应作为优先复盘对象：不要忽略仓位、止损及其与其余持仓的相关性。',
    ],
    notes: [
      '颜色本身不够，请同时阅读分数、标签与底层指标。',
    ],
  },
  'education.risk.beginner.elevated': {
    title: '新手视图：较高风险',
    summary: '当最终动作偏防守（减仓、卖出、回避或告警）时使用的简化标签。',
    usage: '新手模式把动作族映射为短风险标签，便于在不读全套指标时快速扫读。',
    impact: [
      '请放慢：更倾向更小仓位、更清晰止损，或等待更平静的结构再行动。',
    ],
    notes: [
      '这是研究呈现，不是个人适合性评估或投资建议。',
    ],
  },
  'education.risk.beginner.moderate': {
    title: '新手视图：中等风险',
    summary: '当最终动作偏建设或中性（买入、加仓、持有、观察）时使用的简化标签。',
    usage: '即使动作不偏防守，也仍在新手摘要中保持风险可见。',
    impact: [
      '仍需计划：仓位、失效条件与数据局限在中等标签下同样重要。',
    ],
  },
  'education.risk.beginner.unrated': {
    title: '风险待评估',
    summary: '当前动作字段无法映射出简化风险分档。',
    usage: '动作缺失或不在新手映射范围内时显示。',
    impact: [
      '不要默认情况安全——请打开专业详情，或等待完整决策结果。',
    ],
  },
  'education.risk.section': {
    title: '风险与反证',
    summary: '报告中列出风险、失效条件与挑战主结论证据的层级。',
    usage: '放在模型推断之后，帮助你在行动前先看到可能出错之处。',
    impact: [
      '加仓前先读本段；它用来抑制过度自信，而不是替代完整指标。',
    ],
  },
  'education.risk.gate.pass': {
    title: '风险门：通过',
    summary: '强制 Risk Manager 接受了拟发布的最终动作，未改写。',
    usage: '仅表示本轮门禁规则没有强制降级或拒绝，不等于行情预测。',
    impact: [
      '可把最终动作视为未被门禁否决，但仓位与时机仍由你自己负责。',
    ],
    notes: [
      '通过不是收益承诺，也不会消除市场风险。',
    ],
  },
  'education.risk.gate.downgrade': {
    title: '风险门：降级',
    summary: 'Risk Manager 在发布前把原始动作调弱（例如买入→持有）。',
    usage: '当证据或档位阈值要求更谨慎的最终动作时触发。',
    impact: [
      '请以最终动作为准，而不是更激进的原始建议。',
    ],
  },
  'education.risk.gate.reject': {
    title: '风险门：拒绝',
    summary: 'Risk Manager 阻止将原始动作作为最终建议发布。',
    usage: '出现阻断证据或 fail-closed 规则时使用。',
    impact: [
      '不要按原始动作执行；以最终动作与原因码作为系统发布立场。',
    ],
  },
  'education.risk.gate.not_evaluated': {
    title: '风险门：未评估',
    summary: '当前表面没有可信的 Risk Manager 结论。',
    usage: '载荷缺失、畸形或不支持的 schema 时显示——绝不会暗示为通过。',
    impact: [
      '应视为门禁未放行；优先等待或打开诊断，而不是把沉默当成批准。',
    ],
  },
  'education.risk.gate.error': {
    title: '风险门：读取失败',
    summary: 'Web 客户端无法读取本报告或信号的 Risk Manager 结论。',
    usage: '通常是预期路径上的加载或解析失败。',
    impact: [
      '请重试加载报告；在出现裁决前不要当作已过门禁。',
    ],
  },
  'education.risk.gate.loading': {
    title: '风险门：加载中',
    summary: '正在为本表面拉取 Risk Manager 结论。',
    usage: '详情或元数据尚未就绪时的临时状态。',
    impact: [
      '请等待通过、降级、拒绝或未评估后再依据最终动作行动。',
    ],
  },
  'education.portfolio.health': {
    title: '组合结构健康',
    summary: '从已存持仓与历史看，组合在集中度、波动、分散与现金结构上是否均衡。',
    usage: '组合风险视图与健康分总结的是结构，不是单笔交易会不会赚钱。',
    impact: [
      '健康偏弱或热力格偏高时，优先考虑调仓位、相关性或现金，而不是当作买卖指令。',
    ],
    notes: [
      '历史不足时不会伪装成健康的零风险；部分状态会明确展示。',
    ],
  },
  'education.portfolio.var': {
    title: '历史 VaR',
    summary: '用过去收益估计组合在短持有期内可能损失的规模。',
    usage: '仅用已存储日线计算；状态非 ok 时 VaR 为 null，不会显示假零风险。',
    impact: [
      'VaR 越大表示历史上短周期亏损潜力越大——应复盘仓位与对冲，而不是当作价格目标。',
    ],
  },
  'education.portfolio.concentration': {
    title: '集中度',
    summary: '组合价值有多大比例集中在最大持仓（如 HHI 或最大权重）。',
    usage: '集中度高意味着少数标的主导结果。',
    impact: [
      '若单票权重很高，请评估单次不利波动是否仍符合你的计划。',
    ],
  },
  'education.portfolio.diversification': {
    title: '分散化评分',
    summary: '有效暴露在各持仓间分散程度的结构读数。',
    usage: '分散更高通常更少依赖单票；分数低提示持仓过于拥挤。',
    impact: [
      '分散偏低时，加同类风险前应先看相关性和仓位。',
    ],
  },
  'education.indicator.common': {
    title: '技术指标（MA / MACD / RSI）',
    summary: '常用趋势与动量工具：均线（MA）、MACD 与 RSI。',
    usage: '报告可能把技术信号与新闻、基本面一起加权；各展示点旁可打开对应指标的说明。',
    impact: [
      '把指标当作结构与节奏的上下文，而不是单独的买卖指令或收益保证。',
    ],
    notes: [
      'MA、MACD 与 RSI 可能互相矛盾；仍应以风险限额与失效条件为先。',
    ],
  },
  'education.indicator.ma': {
    title: '均线（MA）',
    summary: '过去 N 个交易日收盘价的平均，画成平滑趋势线（如 MA5、MA20）。',
    usage: '价格在上升均线上方常被读作短期偏强，下方偏弱——仍需结合结构。',
    impact: [
      '把均线当作趋势与支撑/阻力参考，而不是单独的买卖指令。',
    ],
    notes: [
      '历史长度不足周期时会省略该均线，而不会用更短窗口冒充。',
    ],
  },
  'education.indicator.macd': {
    title: 'MACD',
    summary: '比较快慢 EMA 与信号线的动量指标（默认 12/26/9）。',
    usage: '金叉/死叉与柱状图方向描述动量变化；它滞后价格，震荡市易反复。',
    impact: [
      '把交叉当作动量提示，与风险与价位一起看，而不是保证入场点。',
    ],
  },
  'education.indicator.rsi': {
    title: 'RSI',
    summary: '用近期涨跌幅度在 0–100 刻度上表达强弱（常见周期 6/12/24）。',
    usage: '高位常提示短期超买压力，低位提示超卖——阈值是惯例而非命运。',
    impact: [
      '极端 RSI 可提示拉伸，但趋势也能持续极端；请结合结构与风险限额。',
    ],
  },

};

export default educationHelpZhCN;
