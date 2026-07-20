# StockPulse 多语言金融术语指导

本文件是 StockPulse 十语言 Web UI 金融术语的**单一治理源**，用于稳定金融概念的产品语义、翻译规则与审查流程，辅助后续多语言翻译，减少同一概念在页面、报告外围、错误、设置和可访问性文案中的漂移。

- 文档正文以简体中文编写，术语表本身覆盖十种界面语言。
- 术语来源以仓库实际实现为准：语言清单以 [`apps/dsa-web/src/i18n/uiLanguages.ts`](../apps/dsa-web/src/i18n/uiLanguages.ts) 为准，界面文案以 [`apps/dsa-web/src/i18n/uiText.ts`](../apps/dsa-web/src/i18n/uiText.ts) 与 [`apps/dsa-web/src/locales/`](../apps/dsa-web/src/locales/) 为准，各语言译文以 [`apps/dsa-web/src/i18n/translations/`](../apps/dsa-web/src/i18n/translations/) 为准。
- 配套约定见 [Web 国际化开发约定](web-i18n.md) / [Web Internationalization Conventions](web-i18n_EN.md)。

## 1. 目的、范围与非目标

**目的**

- 统一 StockPulse 产品内金融概念的语义与推荐表达，为新增/修改 UI 文案的开发者、维护十语言翻译资源的贡献者、审查金融与风险文案的 Reviewer，以及使用 AI 辅助翻译但需人工语义校验的维护者提供单一参考。
- 为后续建立机器可读术语表或自动化检查提供稳定的 `concept_id` 与语义定义。

**范围**

- 只覆盖产品实际使用或近期明确需要的术语；本次以真实代码调查为基础收录约 100 个高价值概念。
- 覆盖领域：市场与行情、技术分析、持仓与账户、回测与绩效、决策信号与风险、告警与通知、AI/模型与设置。

**非目标**

- 不试图定义整个金融行业的唯一翻译，也不替代当地监管、交易所或专业法律意见。
- 不自动翻译用户输入、证券/公司/基金名称、模型 ID、Provider 名、协议标识、路由、API 字段和稳定错误码。
- 不因为建立术语表而承诺投资建议或改变任何风险免责声明；产品内 `AI 建议 / AI signals` 仍是信息性信号，不构成个性化投资建议。
- 本文档只建立治理规则，不批量重写现有翻译资源，也不修改任何运行时代码。

## 2. 权威源与翻译决策顺序

确定某个术语在某语言中的表达时，按以下优先级取证：

1. **产品真实业务语义和代码契约**（本文档 §4 的语义边界、§6 的产品定义与 `concept_id`）。
2. **目标市场监管机构、交易所或权威金融机构的正式用法**（对市场特有概念必须用权威一手来源核对）。
3. **StockPulse 已稳定使用的中英文表达**（`uiText.ts`、`locales/` 的 `zh` / `en` 源文案）。
4. **目标语言金融产品的通行表达**。
5. **机器翻译建议**，仅作为候选，不作为最终证据。

> 引用监管/交易所来源时，只提供必要链接和自己的归纳，不复制长段受版权保护的内容。

## 3. 支持语言范围

以下十种界面语言（UI language）来自 `UI_LANGUAGES`，执行时必须以 [`apps/dsa-web/src/i18n/uiLanguages.ts`](../apps/dsa-web/src/i18n/uiLanguages.ts) 为准。若清单变化，先更新实现，再回填本文并在 PR 说明差异。

| 语言标识 | 语言 | `intlLocale` |
| --- | --- | --- |
| `zh` | 简体中文 | `zh-CN` |
| `zh-TW` | 繁體中文 | `zh-TW` |
| `en` | English | `en-US` |
| `ja` | 日本語 | `ja-JP` |
| `ko` | 한국어 | `ko-KR` |
| `de` | Deutsch | `de-DE` |
| `es` | Español | `es-ES` |
| `ms` | Bahasa Melayu | `ms-MY` |
| `fr` | Français | `fr-FR` |
| `id` | Bahasa Indonesia | `id-ID` |

**报告语言（report language）另有独立且更窄的集合。** 依据 [`apps/dsa-web/src/utils/reportLanguage.ts`](../apps/dsa-web/src/utils/reportLanguage.ts) 的 `getReportLanguageForUi`，模型报告正文只在 `zh` / `en` / `ko` 三种语言生成：`zh` 与 `zh-TW` 映射到 `zh`，`ko` 映射到 `ko`，其余全部映射到 `en`。因此报告正文术语（见 §8）只有这三种语言，与十语言 UI 术语区分开。

## 4. 关键语义边界

任何翻译决策前，先判定文案属于以下哪一类，四类的处理规则完全不同：

| 类别 | 含义 | 处理规则 |
| --- | --- | --- |
| **UI language** | 导航、按钮、表单、错误、提示、可访问性文案，以及日期/数字/货币的显示 locale | 按当前界面语言翻译，覆盖全部十种语言 |
| **report language** | 模型生成的报告正文、正文结构与导出正文 | 只在 `zh` / `en` / `ko` 生成；UI 外围操作仍随 UI language（见 [web-i18n.md](web-i18n.md)） |
| **user content** | 用户输入、股票/公司名称、新闻原文、模型自由文本、第三方策略文本、原始诊断 | 不自动翻译，保持原文 |
| **contract value** | 代码、路由、`id`、`key`、`value`、`filename`、`href`、`url`、`path`、枚举、模型名、Provider、协议、API 字段、稳定错误码 `error` / `message_code` | 不翻译，保持原样 |

后端错误使用统一 envelope：`error` 是稳定业务码，`params` 是本地化插值参数，`message` / `details` / `trace_id` 只用于诊断。前端按 UI language 将 `error + params` 映射为主错误文案。**稳定码与参数属于 contract value，只翻译映射出来的展示文案，不翻译 `error` / `message_code` 本身。** 详见 [web-i18n.md](web-i18n.md) 的“错误与格式化”。

## 5. 术语记录模型

§6 每个领域用两张表表达同一组 `concept_id`，顺序一致：

1. **语义表**：`concept_id` · 产品定义 · 使用上下文 · 禁止/避免表达。
2. **翻译矩阵**：`concept_id` · `en` · `zh` · `zh-TW` · `ja` · `ko` · `de` · `es` · `ms` · `fr` · `id`。

`concept_id` 规则：稳定、语言无关、`snake_case`，按领域加前缀（`mkt_` 市场、`ta_` 技术分析、`pf_` 持仓、`bt_` 回测、`sig_` 决策信号、`al_` 告警通知、`ml_` 模型设置、`rp_` 报告），全表唯一。

**翻译矩阵列的取证状态（重要，避免把未审校译文当成已验证/官方翻译）：**

- `en` / `zh`：**权威**。直接取自产品源文案（`uiText.ts`、`locales/` 的 `en` / `zh`）。
- `zh-TW` / `ja` / `ko` / `de` / `es` / `ms` / `fr` / `id`：为**当前产品内译文基线**，逐字取自 `apps/dsa-web/src/i18n/translations/*.ts`，作为审校起点提供，**均标为 `PENDING_NATIVE_REVIEW`，不是官方、已批准或已完成母语金融审校的翻译**。I18N-01 优先修订但仍待母语审校的概念在 `concept_id` 后标 `⚠`，具体证据见 §7 与 [高风险 i18n 审计](high-risk-i18n-audit.md)。
- 插值占位符（如 `{value}`）逐字保留，各语言参数集合必须一致，不得翻译或增删。

## 6. 核心术语表

> 标 `⚠` 的概念已由 I18N-01 修订明显语义漂移，但候选译文仍需母语金融审校，详见 [§7 I18N-01 候选修订与待审状态](#7-i18n-01-候选修订与待审状态)。

### 6.1 市场与行情

**语义**

| `concept_id` | 产品定义 | 使用上下文 | 禁止/避免 |
| --- | --- | --- | --- |
| `mkt_a_share` | A 股市场（中国内地上市股票） | 告警市场区域、市场筛选 | 不要与“中国概念股/中概股”混用 |
| `mkt_hk_stock` | 港股市场 | 告警市场区域、市场筛选 | — |
| `mkt_us_stock` | 美股市场 | 告警市场区域、市场筛选 | — |
| `mkt_last_price` | 最新成交价/现价 | 持仓明细表头 | 不等于昨收，也不等于结算价 |
| `mkt_change_percent` | 相对参考价的涨跌幅（百分比） | 告警类型、行情展示 | 不要与绝对涨跌额混用 |
| `mkt_market_value` | 单标的或组合的市值 | 持仓明细、组合快照 | 与“成交额”无关 |
| `mkt_turnover_amount` ⚠ | 成交金额（一段时间内成交的货币金额） | 选股候选指标 | 不是成交量（股数），不是换手率 |
| `mkt_turnover_rate` ⚠ | 换手率（成交量 / 流通量） | 个股趋势指标 | 不是成交金额，不是成交量 |
| `mkt_volume_spike` ⚠ | 成交量放大（放量）告警 | 事件告警类型 | “volume”指成交量，非音频音量 |
| `mkt_price_cross` | 价格突破/穿越阈值告警 | 事件告警类型 | 是价格穿越阈值，非泛指“突破” |
| `mkt_fx_status` | 组合估值使用的汇率状态 | 组合快照、汇率刷新 | 指汇率数据状态，非外汇交易 |

**翻译矩阵**

| `concept_id` | `en` | `zh` | `zh-TW` | `ja` | `ko` | `de` | `es` | `ms` | `fr` | `id` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mkt_a_share` | A-shares | A 股 | A 股 | Aシェア | A-쉐어 | A-Aktien | Acciones A | Saham A | Actions A | Saham A |
| `mkt_hk_stock` | Hong Kong | 港股 | 港股 | 香港 | 홍콩 | Hongkong | Hong Kong | Hong Kong | Hong Kong | Hong Kong |
| `mkt_us_stock` | US | 美股 | 美股 | アメリカ合衆国 | 미국 | USA | EE. UU. | US | États-Unis | US |
| `mkt_last_price` | Last price | 现价 | 現價 | 現在値 | 현재가 | Aktueller Kurs | Precio actual | Harga semasa | Cours actuel | Harga saat ini |
| `mkt_change_percent` | Price change | 涨跌幅 | 漲跌幅 | 騰落率 | 등락률 | Kursänderung | Variación | Perubahan harga | Variation | Perubahan harga |
| `mkt_market_value` | Market value | 市值 | 市值 | 市場価値 | 시장 가치 | Marktwert | Valor de mercado | Nilai pasaran | Valeur marchande | Nilai pasar |
| `mkt_turnover_amount` ⚠ | Turnover value | 成交额 | 成交金額 | 売買代金 | 거래대금 | Handelswert | Importe negociado | Nilai dagangan | Montant négocié | Nilai transaksi |
| `mkt_turnover_rate` ⚠ | Turnover rate | 换手率 | 週轉率 | 売買回転率 | 회전율 | Umschlagshäufigkeit | Rotación | Kadar pusing ganti dagangan | Taux de rotation | Tingkat perputaran |
| `mkt_volume_spike` ⚠ | Volume spike | 成交量放大 | 成交量放大 | 出来高急増 | 거래량 급증 | Sprung im Handelsvolumen | Pico de volumen | Lonjakan volum dagangan | Pic du volume des transactions | Lonjakan volume perdagangan |
| `mkt_price_cross` | Price crossing | 价格突破 | 價格穿越 | 価格の閾値クロス | 가격 임계값 교차 | Preisübergang | Cruce de precios | Lintasan harga | Franchissement des prix | Persilangan harga |
| `mkt_fx_status` | FX status | 汇率状态 | 匯率狀態 | FX 状況 | FX 현황 | FX Status | FX Estado | Status FX | FX Statut | Status FX |

### 6.2 技术分析

**语义**

| `concept_id` | 产品定义 | 使用上下文 | 禁止/避免 |
| --- | --- | --- | --- |
| `ta_ma_window` | 均线周期（移动平均窗口长度） | 告警表单参数 | 指周期长度，不是均线值 |
| `ta_rsi` | RSI 指标阈值告警 | 告警类型/表单 | 指标缩写保持 `RSI` |
| `ta_macd` | MACD 金叉/死叉告警 | 告警类型 | 指标缩写保持 `MACD` |
| `ta_kdj` | KDJ 金叉/死叉告警 | 告警类型 | 指标缩写保持 `KDJ` |
| `ta_cci` | CCI 指标阈值告警 | 告警类型 | 指标缩写保持 `CCI` |
| `ta_golden_cross` | 金叉（快线上穿慢线） | 告警方向、交叉方向 | 是技术信号，不承诺上涨 |
| `ta_death_cross` | 死叉（快线下穿慢线） | 告警方向、交叉方向 | 是技术信号，不承诺下跌 |
| `ta_bullish` | 看涨/偏多方向判断 | 回测方向预期 | 是方向判断，不是买入指令 |
| `ta_bearish` | 看跌方向判断 | 回测方向预期 | 是方向判断，不是卖出指令 |
| `ta_heat` ⚠ | 题材/概念热度（关注度） | 选股热点题材 | “heat”指关注度，非温度 |
| `ta_leader` ⚠ | 龙头股（领涨/代表个股） | 选股热点题材 | 指龙头个股，非人物“leader” |

**翻译矩阵**

| `concept_id` | `en` | `zh` | `zh-TW` | `ja` | `ko` | `de` | `es` | `ms` | `fr` | `id` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ta_ma_window` | MA window | 均线周期 | 均線週期 | MAウィンドウ | MA 창 | MA-Fenster | Ventana MA | Tetingkap MA | Fenêtre MA | Jendela MA |
| `ta_rsi` | RSI threshold | RSI 阈值 | RSI 閾值 | RSI閾値 | RSI 임계값 | RSI-Schwelle | Umbral RSI | Ambang RSI | Seuil RSI | Ambang batas RSI |
| `ta_macd` | MACD cross | MACD 金叉/死叉 | MACD 金叉/死叉 | MACD ゴールデンクロス／デッドクロス | MACD 골든크로스/데드크로스 | MACD-Kreuz | Cruce MACD | Salib MACD | Croisement MACD | Persilangan MACD |
| `ta_kdj` | KDJ cross | KDJ 金叉/死叉 | KDJ 金叉/死叉 | KDJ ゴールデンクロス／デッドクロス | KDJ 골든크로스/데드크로스 | KDJ-Kreuzung | Cruce KDJ | Salib KDJ | Croix KDJ | Persilangan KDJ |
| `ta_cci` | CCI threshold | CCI 阈值 | CCI 閾值 | CCI閾値 | CCI 임계값 | CCI-Schwelle | Umbral CCI | Ambang CCI | Seuil CCI | Ambang batas CCI |
| `ta_golden_cross` | bullish cross | 金叉 | 金叉 | ゴールデンクロス | 골든크로스 | bullische Kreuzung | cruce alcista | persilangan menaik | croisement haussier | Persilangan bullish |
| `ta_death_cross` | bearish cross | 死叉 | 死叉 | デッドクロス | 데드크로스 | bärische Kreuzung | Cruce bajista | persilangan menurun | Croisement baissier | persilangan bearish |
| `ta_bullish` | Bullish | 看涨 | 看漲 | 強気 | 강세 | Bullisch | Alcista | Menaik harga | Haussier | Bullish |
| `ta_bearish` | Bearish | 看跌 | 看跌 | 弱気 | 약세 | Bärisch | Bajista | Menurun | Baissier | Bearish |
| `ta_heat` ⚠ | Theme interest | 热度 | 熱度 | 注目度 | 관심도 | Beliebtheit | Popularidad | Populariti | Popularité | Popularitas |
| `ta_leader` ⚠ | Leading stock | 龙头 | 龍頭 | 牽引銘柄 | 주도주 | Führungsaktie | Valor líder | Saham peneraju | Valeur phare | Saham unggulan |

### 6.3 持仓与账户

**语义**

| `concept_id` | 产品定义 | 使用上下文 | 禁止/避免 |
| --- | --- | --- | --- |
| `pf_portfolio` | 持仓/组合管理页 | 页面标题 | 组合（portfolio）不是单个账户（account） |
| `pf_account` | 持仓账户 | 账户视图、录入 | 账户不等于组合 |
| `pf_positions` | 持仓明细 | 持仓明细区块 | 持仓（position）不是持仓账户 |
| `pf_avg_cost` | 均价（单标的持仓均价） | 持仓明细表头 | 是持仓成本单价，非平均费用 |
| `pf_cost_method` ⚠ | 成本口径（FIFO / 均价） | 组合快照参数 | 是成本核算方法，不是“成本基础”本身 |
| `pf_fifo` | 先进先出成本法 | 成本口径选项 | 缩写保持 `FIFO` |
| `pf_avg_cost_basis` ⚠ | 均价成本法 | 成本口径选项 | 是成本法，不是“平均费用/开销” |
| `pf_unrealized_pnl` | 未实现盈亏（浮动盈亏） | 持仓明细表头 | 不得与已实现盈亏混淆 |
| `pf_return_pct` | 收益率（百分比） | 持仓明细表头 | 与绝对盈亏额区分 |
| `pf_total_equity` | 总权益 | 组合快照 | 权益 ≠ 市值 ≠ 现金 |
| `pf_total_cash` | 总现金 | 组合快照 | 现金 ≠ 权益 |
| `pf_quote_currency` | 计价币种 | 组合快照口径 | 是计价货币，非基准币输入项 |
| `pf_sector_concentration` | 行业集中度分布 | 风险模块 | 集中度是风险指标，非配置比例 |
| `pf_max_drawdown` | 最大回撤 | 回撤监控 | 回撤是风险，不承诺未来 |
| `pf_current_drawdown` | 当前回撤 | 回撤监控 | 与最大回撤区分 |
| `pf_side` ⚠ | 买卖方向 | 交易录入 | “side”指买/卖方向，非“边/部分” |
| `pf_fee` | 手续费 | 交易录入 | 与税费分列 |
| `pf_cash_flow` | 资金流水（出入金） | 事件记录 | 资金流水 ≠ 交易流水 |
| `pf_corporate_action` | 公司行为（分红/拆并股等） | 事件记录 | 是公司行为事件，非用户交易 |
| `pf_cash_dividend` | 现金分红 | 公司行为类型 | — |
| `pf_split_adjustment` | 拆并股调整 | 公司行为类型 | 是股本调整，非价格错误 |

**翻译矩阵**

| `concept_id` | `en` | `zh` | `zh-TW` | `ja` | `ko` | `de` | `es` | `ms` | `fr` | `id` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pf_portfolio` | Portfolio management | 持仓管理 | 持倉管理 | ポートフォリオ管理 | 포트폴리오 관리 | Portfoliomanagement | Gestión de carteras | Pengurusan portfolio | Gestion de portefeuille | Manajemen portofolio |
| `pf_account` | Account | 账户 | 賬戶 | アカウント | 계정 | Konto | Cuenta | Akaun | Compte | Akun |
| `pf_positions` | Positions | 持仓明细 | 持倉明細 | ポジション | 보유 포지션 | Positionen | Posiciones | Pegangan | Positions | Posisi |
| `pf_avg_cost` | Avg cost | 均价 | 平均成本 | 平均取得単価 | 평균 매입가 | Durchschnittlicher Einstandskurs | Precio medio de compra | Harga belian purata | Prix de revient moyen | Harga beli rata-rata |
| `pf_cost_method` ⚠ | Cost method | 成本口径 | 成本口徑 | 取得価額計算方法 | 취득원가 계산 방식 | Anschaffungskostenmethode | Método de cálculo del coste | Kaedah kos pemerolehan | Méthode de calcul du coût | Metode biaya perolehan |
| `pf_fifo` | FIFO | 先进先出（FIFO） | 先進先出（FIFO） | FIFO | FIFO | FIFO | FIFO | FIFO | FIFO | FIFO |
| `pf_avg_cost_basis` ⚠ | Average cost | 均价成本（AVG） | 均價成本（AVG） | 平均取得価額 | 평균 매입단가 | Durchschnittskostenmethode | Método de coste medio | Kaedah kos purata | Méthode du coût moyen | Metode biaya rata-rata |
| `pf_unrealized_pnl` | Unrealized P/L | 未实现盈亏 | 未實現盈虧 | 未実現損益 | 실현되지 않은 손익 | Nicht realisierter Gewinn/Verlust | P/L no realizado | Untung/rugi belum direalisasi | P/L non réalisé | Laba/rugi belum terealisasi |
| `pf_return_pct` | Return | 收益率 | 報酬率 | 収益率 | 수익률 | Rendite | Rentabilidad | Pulangan | Rendement | Imbal hasil |
| `pf_total_equity` | Total equity | 总权益 | 總權益 | 純資産 | 총자산 | Gesamteigenkapital | Patrimonio total | Jumlah ekuiti | Capitaux propres totaux | Total ekuitas |
| `pf_total_cash` | Total cash | 总现金 | 總現金 | 総現金 | 총 현금 | Barmittel gesamt | Total de efectivo | Jumlah tunai | Total de trésorerie | Total uang tunai |
| `pf_quote_currency` | Quote currency | 计价币种 | 計價幣種 | 建値通貨 | 표시 통화 | Notierungswährung | Moneda de cotización | Sebut harga mata wang | Devise de cotation | Mata uang kutipan |
| `pf_sector_concentration` | Sector concentration | 行业集中度分布 | 行業集中度分佈 | セクター集中 | 부문 집중 | Sektorkonzentration | Concentración sectorial | Kepekatan sektor | Concentration sectorielle | Konsentrasi sektor |
| `pf_max_drawdown` | Max drawdown | 最大回撤 | 最大回撤 | 最大ドローダウン | 최대 낙폭 | Maximaler Drawdown | Drawdown máximo | Susutan maksimum | Repli maximal | Drawdown maksimum |
| `pf_current_drawdown` | Current drawdown | 当前回撤 | 目前回撤 | 現在のドローダウン | 현재 낙폭 | Aktueller Drawdown | Drawdown actual | Susutan semasa | Repli actuel | Drawdown saat ini |
| `pf_side` ⚠ | Trade side | 买卖方向 | 買賣方向 | 売買区分 | 매매 구분 | Handelsrichtung | Dirección de la operación | Arah dagangan | Sens de la transaction | Arah transaksi |
| `pf_fee` | Fee | 手续费 | 手續費 | 手数料 | 수수료 | Gebühr | Tarifa | Yuran | Frais | Biaya |
| `pf_cash_flow` | Cash flows | 资金流水 | 資金流水 | キャッシュフロー | 현금 흐름 | Cashflows | Flujos de caja | Aliran tunai | Flux de trésorerie | Arus kas |
| `pf_corporate_action` | Corporate actions | 公司行为 | 公司行為 | 企業行動 | 기업 활동 | Gesellschaftsmaßnahmen | Acciones corporativas | Tindakan korporat | Actions sur les sociétés | Aksi korporasi |
| `pf_cash_dividend` | Cash dividend | 现金分红 | 現金分紅 | 現金配当 | 현금 배당 | Bardividende | Dividendo en efectivo | Dividen tunai | Dividende en espèces | Dividen tunai |
| `pf_split_adjustment` | Split adjustment | 拆并股调整 | 拆並股調整 | 分割調整 | 분할 조정 | Split-Anpassung | Ajuste de división | Pelarasan pecahan saham | Réglage de la fraction | Penyesuaian pemecahan saham |

### 6.4 回测与绩效

**语义**

| `concept_id` | 产品定义 | 使用上下文 | 禁止/避免 |
| --- | --- | --- | --- |
| `bt_backtest` | 策略回测页 | 页面标题 | 回测是历史验证，不预测未来 |
| `bt_win_rate` | 胜率 | 整体表现指标 | 胜率不是收益保证 |
| `bt_direction_accuracy` | 方向准确率 | 整体表现指标 | 是历史统计，非未来承诺 |
| `bt_window_return` | 评估窗口内收益 | 结果表 | 历史区间收益，非预期收益 |
| `bt_eval_window` | 评估窗口（交易日数） | 回测参数 | 是评估天数，非持仓周期 |
| `bt_ai_prediction` | AI 历史预测（被回测对象） | 结果表 | 预测是被验证项，非确定结论 |
| `bt_actual_performance` | 实际表现（对照 AI 预测） | 结果表 | 实际值 ≠ 预测值 |
| `bt_next_day_validation` | 次日验证模式 | 1 日验证 | 单日校验，非完整回测 |
| `bt_stop_loss_trigger_rate` | 止损触发率 | 整体表现指标 | 是统计频率，非当前持仓状态 |
| `bt_take_profit_trigger_rate` | 止盈触发率 | 整体表现指标 | 是统计频率 |
| `bt_long` | 做多方向 | 方向预期 | 是方向，不是买入建议 |
| `bt_cash` | 空仓（不持仓） | 方向预期 | 空仓 ≠ 卖空 |

**翻译矩阵**

| `concept_id` | `en` | `zh` | `zh-TW` | `ja` | `ko` | `de` | `es` | `ms` | `fr` | `id` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `bt_backtest` | Strategy Backtest | 策略回测 | 策略回測 | 戦略バックテスト | 전략 백테스트 | Strategie-Backtest | Backtest de estrategia | Ujian balik strategi | Backtest de stratégie | Backtest strategi |
| `bt_win_rate` | Win rate | 胜率 | 勝率 | 勝率 | 승률 | Gewinnrate | Tasa de victorias | Kadar kemenangan | Taux de victoire | Tingkat kemenangan |
| `bt_direction_accuracy` | Direction accuracy | 方向准确率 | 方向準確率 | 方向精度 | 방향 정확도 | Richtungsgenauigkeit | Precisión de dirección | Ketepatan arah | Précision de la direction | Akurasi arah |
| `bt_window_return` | Window return | 窗口收益 | 區間報酬率 | 期間収益率 | 기간 수익률 | Rendite im Zeitraum | Rentabilidad del período | Pulangan tempoh | Rendement sur la période | Imbal hasil periode |
| `bt_eval_window` | Evaluation window | 评估窗口 | 評估視窗 | 評価ウィンドウ | 평가 창 | Bewertungsfenster | Ventana de evaluación | Tetingkap penilaian | Fenêtre d’évaluation | Jendela evaluasi |
| `bt_ai_prediction` | AI prediction | AI 预测 | AI 預測 | AI予測 | AI 예측 | KI-Vorhersage | Predicción de IA | Ramalan AI | Prédiction IA | Prediksi AI |
| `bt_actual_performance` | Actual performance | 实际表现 | 實際表現 | 実際の運用成績 | 실제 투자 성과 | Tatsächliche Leistung | Rendimiento real | Prestasi sebenar | Performance réelle | Performa aktual |
| `bt_next_day_validation` | Next-day validation | 次日验证 | 次日驗證 | 翌日検証 | 다음 날 검증 | Validierung am nächsten Tag | Validación al día siguiente | Pengesahan hari berikutnya | Validation du lendemain | Validasi hari berikutnya |
| `bt_stop_loss_trigger_rate` | Stop-loss trigger rate | 止损触发率 | 止損觸發率 | ストップロストリガーレート | 스톱로스 트리거 레이트 | Stop-Loss-Auslöserrate | Tasa de disparo de stop-loss | Kadar pencetus henti rugi | Taux de déclenchement stop-loss | Tingkat pemicu stop-loss |
| `bt_take_profit_trigger_rate` | Take-profit trigger rate | 止盈触发率 | 止盈觸發率 | 利益取りトリガーレート | 이익 실현 트리거 레이트 | Take-Profit-Triggerrate | Tasa de activación del take profit | Kadar pencetus ambil untung | Taux de déclenchement du take profit | Tingkat pemicu take-profit |
| `bt_long` | Long | 做多 | 做多 | ロング | 롱 | Long-Position | Posición larga | Posisi beli | Position longue | Posisi beli |
| `bt_cash` | Cash | 空仓 | 空倉 | ノーポジション | 미보유 | Keine Position | Sin posición | Tiada pegangan | Aucune position | Tanpa posisi |

### 6.5 决策信号与风险

产品把该模块命名为 `AI 建议 / AI signals`，但它是**信息性决策信号**，不构成个性化投资建议。`buy` / `sell` / `target price` 等词只表达信息语义，禁止翻译成保证收益、确定性指令或受监管的个性化投资建议（见 §10）。

**语义**

| `concept_id` | 产品定义 | 使用上下文 | 禁止/避免 |
| --- | --- | --- | --- |
| `sig_ai_signals` | AI 决策信号池 | 决策信号页标题 | 是信息信号，非投资建议 |
| `sig_action` | 建议动作字段 | 信号列/表头 | 动作是信息判断，非指令 |
| `sig_action_buy` | 动作：买入 | 历史/信号动作 | 不是保证盈利的买入指令 |
| `sig_action_hold` | 动作：持有 | 历史/信号动作 | — |
| `sig_action_sell` | 动作：卖出 | 历史/信号动作 | 不是保证的卖出指令 |
| `sig_action_add` | 动作：加仓 | 历史/信号动作 | 与买入区分（已有持仓上增） |
| `sig_action_reduce` | 动作：减仓 | 历史/信号动作 | 与卖出区分（部分减少） |
| `sig_action_watch` | 动作：观望 | 历史/信号动作 | 观望不是买卖指令 |
| `sig_action_avoid` ⚠ | 动作：回避 | 历史/信号动作 | 应为名词化标签，非祈使句 |
| `sig_confidence` ⚠ | 信号置信度 | 信号详情 | 是模型置信度，非“自信心” |
| `sig_score` | 信号评分 | 信号详情、选股 | 评分是相对分值，非确定结论 |
| `sig_target_price` | 目标价 | 信号详情 | 是参考目标，非价格承诺 |
| `sig_stop_loss` | 止损价 | 信号详情 | 是风险控制点，非确定触发 |
| `sig_catalyst` | 催化因素 | 信号/选股 | 催化不等于确定利好 |
| `sig_signal` | 操作信号 | 选股候选 | 信息性信号，非指令 |
| `sig_risk_tags` | 风险标签 | 选股候选 | 是风险提示，非评级背书 |
| `sig_primary_factors` | 主要因子 | 选股候选 | 因子是评分依据，非结论 |

**翻译矩阵**

| `concept_id` | `en` | `zh` | `zh-TW` | `ja` | `ko` | `de` | `es` | `ms` | `fr` | `id` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sig_ai_signals` | AI signals | AI 建议 | AI 建議 | AI信号 | AI 신호 | KI-Signale | Señales de IA | Isyarat AI | Signaux IA | Sinyal AI |
| `sig_action` | Action | 动作 | 動作 | アクション | 조치 | Aktion | Acción | Tindakan | Action | Tindakan |
| `sig_action_buy` | Buy | 买入 | 買入 | 買い | 매수 | Kauf | Compra | Beli | Acheter | Beli |
| `sig_action_hold` | Hold | 持有 | 持有 | 保有 | 보유 | Halten | Mantener | Pegang | Conserver | Tahan |
| `sig_action_sell` | Sell | 卖出 | 賣出 | 売り | 매도 | Verkauf | Vender | Jual | Vendre | Jual |
| `sig_action_add` | Add | 加仓 | 加碼 | 買い増し | 비중 확대 | Position aufstocken | Aumentar posición | Tambah pegangan | Renforcer la position | Tambah posisi |
| `sig_action_reduce` | Reduce | 减仓 | 減碼 | ポジション縮小 | 비중 축소 | Position reduzieren | Reducir posición | Kurangkan pegangan | Réduire la position | Kurangi posisi |
| `sig_action_watch` | Watch | 观望 | 觀望 | 様子見 | 관망 | Abwarten | Esperar | Tunggu dan lihat | Attendre | Tunggu |
| `sig_action_avoid` ⚠ | Avoid | 回避 | 迴避 | 見送り | 회피 | Meiden | Evitar | Elak | Éviter | Dihindari |
| `sig_confidence` ⚠ | Confidence | 置信度 | 置信度 | 信頼度 | 신뢰도 | Konfidenz | Nivel de confianza | Tahap keyakinan | Niveau de confiance | Tingkat keyakinan |
| `sig_score` ⚠ | Score | 评分 | 評分 | スコア | 점수 | Punktzahl | Puntuación | Skor | Score | Skor |
| `sig_target_price` | Target price | 目标价 | 目標價 | 目標価格 | 목표 가격 | Zielpreis | Precio objetivo | Harga sasaran | Prix cible | Harga target |
| `sig_stop_loss` | Stop loss | 止损 | 停損 | 損切り | 손절 | Stop-Loss | Límite de pérdidas | Henti rugi | Stop-loss | Batas rugi |
| `sig_catalyst` | Catalyst | 催化 | 催化 | カタリスト | 촉매제 | Katalysator | Catalizador | Pemangkin | Catalyseur | Katalis |
| `sig_signal` | Signal | 操作信号 | 操作訊號 | 信号 | 신호 | Signal | Señal | Isyarat | Signal | Sinyal |
| `sig_risk_tags` | Risk tags | 风险标签 | 風險標籤 | リスクタグ | 위험 태그 | Risiko-Tags | Etiquetas de riesgo | Tag risiko | Étiquettes de risque | Tag risiko |
| `sig_primary_factors` | Primary factors | 主要因子 | 主要因子 | 主な要因 | 주요 요인 | Hauptfaktoren | Factores principales | Faktor utama | Facteurs principaux | Faktor utama |

### 6.6 告警与通知

**语义**

| `concept_id` | 产品定义 | 使用上下文 | 禁止/避免 |
| --- | --- | --- | --- |
| `al_create_rule` | 创建告警规则 | 告警中心 | — |
| `al_portfolio_drawdown` | 组合回撤告警 | 告警类型 | 与个股回撤区分 |
| `al_severity_info` ⚠ | 严重级别：提示 | 告警级别 | “Info”是提示级别，非“小费/建议” |
| `al_severity_warning` | 严重级别：警告 | 告警级别 | — |
| `al_severity_critical` | 严重级别：严重 | 告警级别 | — |
| `al_watchlist` ⚠ | 自选股范围 | 告警目标范围 | 是“自选股清单”，非冗长直译 |
| `al_enabled` | 规则已启用 | 规则状态 | — |
| `al_disabled` | 规则已停用 | 规则状态 | “已停用”非“从未启用” |
| `al_cooldown` | 冷却时间（去重抑制） | 规则状态 | 是业务冷却，非游戏“充能” |
| `al_trigger_history` ⚠ | 触发历史记录 | 告警历史 | 是“记录/履历”，非宏大“历史” |
| `al_notify_configured` | 通知渠道已配置 | 通知设置 | — |
| `al_notify_unconfigured` | 通知渠道未配置 | 通知设置 | — |

**翻译矩阵**

| `concept_id` | `en` | `zh` | `zh-TW` | `ja` | `ko` | `de` | `es` | `ms` | `fr` | `id` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `al_create_rule` | Create alert rule | 创建告警规则 | 建立告警規則 | アラートルールを作成する | 경고 규칙 생성 | Alarmregel erstellen | Crear regla de alerta | Cipta peraturan makluman | Règle de création d’alerte | Membuat aturan pemberitahuan |
| `al_portfolio_drawdown` | Portfolio drawdown | 组合回撤 | 組合回撤 | ポートフォリオドローダウン | 포트폴리오 낙폭 | Portfolio-Drawdown | Drawdown de cartera | Susutan portfolio | Repli du portefeuille | Drawdown portofolio |
| `al_severity_info` ⚠ | Info | 提示 | 提示 | 情報 | 정보 | Information | Información | Maklumat | Information | Informasi |
| `al_severity_warning` | Warning | 警告 | 警告 | 警告 | 경고 | Warnung | Advertencia | Amaran | Avertissement | peringatan |
| `al_severity_critical` | Critical | 严重 | 嚴重 | 重大 | 심각 | Kritisch | Crítica | Kritikal | Critique | Kritis |
| `al_watchlist` ⚠ | Watchlist | 自选股 | 自選股 | ウォッチリスト | 관심 종목 | Watchlist | Lista de seguimiento | Senarai pantau | Liste de suivi | Daftar pantauan |
| `al_enabled` | Enabled | 已启用 | 已啟用 | 有効化 | 활성화됨 | Aktiviert | Habilitado | Didayakan | Activé | Diaktifkan |
| `al_disabled` ⚠ | Disabled | 已停用 | 已停用 | 無効 | 비활성화 | Deaktiviert | Desactivado | Dilumpuhkan | Désactivé | Dinonaktifkan |
| `al_cooldown` ⚠ | Cooldown | 冷却 | 冷卻時間 | 抑制期間 | 재알림 대기 시간 | Sperrfrist | Período de espera | Tempoh penangguhan | Délai de temporisation | Jeda notifikasi |
| `al_trigger_history` ⚠ | Trigger history | 触发历史 | 觸發記錄 | トリガー履歴 | 트리거 기록 | Auslöseverlauf | Historial de activaciones | Rekod pencetus | Historique des déclenchements | Riwayat pemicu |
| `al_notify_configured` | Configured | 已配置 | 已配置 | 構成済み | 구성 | Konfiguriert | Configurado | Dikonfigurasikan | Configuré | Dikonfigurasi |
| `al_notify_unconfigured` | Not configured | 未配置 | 未配置 | 設定されていません | 설정 안 됨 | Nicht konfiguriert | No configurado | Tidak dikonfigurasikan | Non configuré | Tidak dikonfigurasi |

### 6.7 AI、模型与设置

**语义**

| `concept_id` | 产品定义 | 使用上下文 | 禁止/避免 |
| --- | --- | --- | --- |
| `ml_provider` | 模型服务商（Provider） | 模型接入 | Provider 名称是契约值，不翻译 |
| `ml_protocol` | 连接协议 | 模型接入 | 协议标识保持原样 |
| `ml_base_url` | 服务地址（Base URL） | 模型接入 | URL 是契约值，只翻译字段名 |
| `ml_api_key` | API 密钥 | 模型接入 | 密钥值不显示、不翻译 |
| `ml_connection_name` | 连接名称 | 模型接入 | 连接名是用户输入内容 |
| `ml_available_models` | 可用模型列表 | 模型接入 | 模型 ID 是契约值，不翻译 |
| `ml_test_connection` | 测试连接 | 模型接入 | — |

**翻译矩阵**

| `concept_id` | `en` | `zh` | `zh-TW` | `ja` | `ko` | `de` | `es` | `ms` | `fr` | `id` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ml_provider` | Model provider | 模型服务商 | 模型服務商 | モデルプロバイダー | 모델 제공자 | Modellanbieter | Proveedor de modelos | Pembekal model | Fournisseur de modèles | Penyedia model |
| `ml_protocol` | Protocol | 协议 | 協議 | プロトコル | 프로토콜 | Protokoll | Protocolo | Protokol | Protocole | Protokol |
| `ml_base_url` | Base URL | 服务地址 | 服務地址 | ベースURL | 기본 URL | Basis-URL | Base URL | URL asas | URL de base | URL dasar |
| `ml_api_key` | API key | API 密钥 | API 金鑰 | API キー | API 키 | API-Schlüssel | Clave API | Kunci API | Clé API | Kunci API |
| `ml_connection_name` | Connection name | 连接名称 | 連線名稱 | 接続名 | 연결 명칭 | Verbindungsname | Nombre de la conexión | Nama sambungan | Nom de la connexion | Nama koneksi |
| `ml_available_models` | Available models | 可用模型 | 可用模型 | 利用可能なモデル | 사용 가능한 모델 | Verfügbare Modelle | Modelos disponibles | Model yang tersedia | Modèles disponibles | Model yang tersedia |
| `ml_test_connection` | Test connection | 测试连接 | 測試連線 | テスト接続 | 테스트 연결 | Testverbindung | Conexión de prueba | Sambungan ujian | Connexion d’essai | Uji koneksi |

## 7. I18N-01 候选修订与待审状态

I18N-01 已修订下表中的明显语义漂移，并通过高风险语义守卫锁定当前 key 集合与十语言 bundle 快照。修订值是基于产品契约、一手机构术语和自动化语义审查得到的**候选产品译文**，不是母语金融签核。除 `zh` / `en` 产品源文案外，八个翻译 bundle 仍统一标记为 `PENDING_NATIVE_REVIEW`；完整来源、基线 SHA、逐语言状态和 `before` / `recommended` 记录见 [High-risk i18n semantic audit](high-risk-i18n-audit.md) 与机器清单 `apps/dsa-web/scripts/high-risk-i18n-audit.json`。

| 概念组 | 旧值样本 | 当前候选语义 | 审查状态 |
| --- | --- | --- | --- |
| 成交量 / 成交额 / 换手率 | 音量の急増、Lautstärkespitze、两个 “Turnover” | 明确区分 trading volume、turnover value、turnover rate | 八个翻译 bundle 均 `PENDING_NATIVE_REVIEW` |
| 题材热度 / 龙头股 | Hitze、Calor、Chef、Anführer | 市场关注度与领涨个股，不指温度或人物 | 八个翻译 bundle 均 `PENDING_NATIVE_REVIEW` |
| 成本口径 / 买卖方向 | コストベースアプローチ、Bahagian、Sisi | 成本核算方法与 buy/sell transaction direction | 八个翻译 bundle 均 `PENDING_NATIVE_REVIEW` |
| 信号动作 / 置信度 / 评分 | 避けてください、Selbstvertrauen、Classement | 信息性状态标签、模型置信度、数值评分 | 八个翻译 bundle 均 `PENDING_NATIVE_REVIEW` |
| 告警提示 / 自选股 / 冷却 / 触发记录 | Propina、自己選択株、Temps de recharge、Auslösergeschichte | 信息级别、watchlist、抑制期、触发记录 | 八个翻译 bundle 均 `PENDING_NATIVE_REVIEW` |
| API key / provider key / CLI 登录状态 | API Legende、touches、teclas、缺失 provider-key 路径与断裂的凭据文件说明 | 区分 API key、legacy provider key、StockPulse 凭据访问和 CLI 自身登录状态 | 八个翻译 bundle 均 `PENDING_NATIVE_REVIEW` |
| AlphaSift 风险提示 | 断裂机翻与责任主体不清 | 保留“研究/辅助判断”“不构成投资建议”“决策和结果由用户承担”三层 | 八个翻译 bundle 均 `PENDING_NATIVE_REVIEW` |

仍未统一的低风险市场别名（例如股票搜索 `China` 与告警区域 `A-shares`）不在本次高风险修订范围内，继续作为后续产品命名收敛项；不得据此把本次候选翻译标为母语审校完成。

## 8. 报告语言术语（仅 `zh` / `en` / `ko`）

报告正文只在 `zh` / `en` / `ko` 生成（见 §3），其余七种界面语言在报告正文中回退到 `en`。以下术语来自 [`apps/dsa-web/src/utils/reportLanguage.ts`](../apps/dsa-web/src/utils/reportLanguage.ts)，属于 report language，不进入十语言 UI 矩阵。

| `concept_id` | 产品定义 | `en` | `zh` | `ko` |
| --- | --- | --- | --- | --- |
| `rp_key_insights` | 核心洞察分区 | KEY INSIGHTS | 核心洞察 | 핵심 인사이트 |
| `rp_action_advice` | 操作建议分区 | Action Advice | 操作建议 | 대응 전략 |
| `rp_trend_outlook` | 趋势预测分区 | Trend Outlook | 趋势预测 | 추세 전망 |
| `rp_market_sentiment` | 市场情绪分区 | Market Sentiment | 市场情绪 | 시장 심리 |
| `rp_strategy_points` | 策略点位分区 | STRATEGY POINTS | 策略点位 | 전략 가격대 |
| `rp_action_levels` | 关键操作点位（源 key `sniperLevels`） | Action Levels | 狙击点位 | 대응 가격대 |
| `rp_ideal_entry` | 理想买入点 | Ideal Entry | 理想买入 | 이상적 매수가 |
| `rp_secondary_entry` | 二次买入点 | Secondary Entry | 二次买入 | 추가 매수가 |
| `rp_stop_loss` | 报告止损价位 | Stop Loss | 止损价位 | 손절가 |
| `rp_take_profit` | 报告止盈目标 | Take Profit | 止盈目标 | 목표가 |
| `rp_fear_greed_index` | 恐惧贪婪指数 | Fear & Greed Index | 恐惧贪婪指数 | 공포·탐욕 지수 |
| `rp_board_linkage` | 板块联动分区 | BOARD LINKAGE | 板块联动 | 섹터 연동 |
| `rp_leading_board` | 领涨板块 | Leading | 领涨 | 강세 |
| `rp_lagging_board` | 领跌板块 | Lagging | 领跌 | 약세 |

> `rp_action_levels`：源 key 为 `sniperLevels`（中文“狙击点位”），`en` 与 `ko` 已刻意去军事化译为 “Action Levels / 대응 가격대”。这是**语义对齐优先于字面**的范例——`en`/`ko` 不复制中文的“狙击”隐喻，而对齐产品实义（关键操作点位）。新增语言时应对齐实义，避免直译“狙击/sniper”。

## 9. 不翻译 / 谨慎翻译清单

以下内容属于 contract value 或 user content，**保持原样，不翻译**：

- **标识类**：股票代码、交易所代码、`ISIN` 等证券标识；`id`、`key`、`value`、`filename`、`href`、`url`、`route`、`path` 字段；`localStorage` key（如 `dsa.uiLanguage`）。
- **技术标识**：`Provider` 名、模型 ID / 模型路由、协议名、`API`、`Webhook`、`URL`、`JSON`、`CSV`、`OAuth`、`RSI` / `MACD` / `KDJ` / `CCI` 等指标缩写。
- **错误与状态码**：稳定错误码 `error`、任务 `message_code`、枚举值（如 `bullish_cross`、`portfolio_stop_loss`）。只翻译由 `error + params` / `message_code + message_params` 映射出的**展示文案**，不翻译码本身。
- **用户内容**：用户输入、股票/公司/基金/指数官方名称（优先使用数据源原文或官方本地名称）、新闻原文、模型自由文本、第三方策略自由文本、原始诊断（`message` / `details` / `trace_id`）。
- **整句配置提示**：如模型配置只读提示（源 key `readonly`）是完整句子而非术语，按普通 UI 文案整句翻译，不拆词进术语表。

谨慎处理：

- 缩写首次出现可在括号内补全整称一次（如 “换手率（Turnover rate）”），短标签和空间受限处只用缩写。
- 混合了代码与文案的插值（如 `分析 {symbol}`）只翻译文案部分，`{symbol}` 保持原样。

## 10. 风险语义与禁止表达

金融与合规敏感，翻译中**必须避免**以下表达：

- 保证收益、稳赚、无风险、确定上涨/下跌等承诺性措辞。
- 把概率、评分或信心（`sig_score` / `sig_confidence`）误译为“事实/确定结论”。
- 把信息性信号（`sig_ai_signals`、`sig_action_*`）翻译为直接、个性化的投资建议或指令。
- 把回测表现（§6.4）表述为未来收益承诺；`bt_*` 全部是历史统计。
- 混淆 `pf_unrealized_pnl`（未实现）与已实现盈亏。
- 混淆 `pf_positions` / holding、`pf_portfolio` 与 `pf_account`。
- 混淆 `mkt_turnover_amount`（成交额）、`mkt_turnover_rate`（换手率）与成交量（volume）。
- 混淆 `sig_target_price`（目标价，参考）与预测/估计/保证。
- 用情绪化或营销化表达替代中性金融语言。

产品已有的风险免责基线必须保持语义（源文案，`zh` / `en`）：

> 实验功能与风险提示：选股结果仅用于研究和辅助判断，不构成投资建议；市场有风险，交易决策和损益由使用者自行承担。
>
> AlphaSift screening is experimental and intended only for research and decision support. It is not investment advice. You are responsible for trading decisions and outcomes.

各语言必须保留“仅供研究/辅助判断”“不构成投资建议”“风险自负”三层语义，不得弱化或删除。

## 11. 数字、日期、货币、百分比与正负号

与 [`apps/dsa-web/src/utils/uiLocale.ts`](../apps/dsa-web/src/utils/uiLocale.ts) 保持一致：

- **显示 Locale 与市场业务时区分离**：显示按 `UI_LANGUAGE_METADATA[lang].intlLocale` 用 `Intl` 格式化（`formatUiDateTime` / `formatUiNumber` / `formatUiCurrency` / `formatUiList`）；市场交易日、盘前/盘中/盘后按市场时区判定，不按浏览器时区。
- **机器格式保持原样**：ISO 日期、表单值、股票代码、模型 ID 不做本地化。
- **货币**：`formatUiCurrency` 使用 `currencyDisplay: 'code'`（显示币种代码如 `CNY` / `USD` / `HKD`），不要在文案中臆造货币符号。
- **分隔符按语言**：列表分隔符 `zh` / `zh-TW` / `ja` 用 `、`，其余用 `, `；分句 `zh` / `zh-TW` 用 `；`，其余用 `; `；冒号 `zh` / `zh-TW` / `ja` 用 `：`，其余用 `: `。
- **百分比、正负号与零值**：涨跌幅、收益率、回撤为百分比；正负号与零值（`0` / `—`）表达要清晰，空值/未知/不可用/延迟数据用统一占位（源用 `—`）。
- **颜色语义不可只靠颜色**：A 股“红涨绿跌”与国际“绿涨红跌”相反，涨跌必须同时用符号/文字表达，不能只靠颜色。

## 12. 文案风格与 UI 空间约束

- 标签短、说明完整、错误可行动；按钮用动作动词（`al_create_rule`、`ml_test_connection`）。
- 避免在标签中堆叠多层括号；缩写整称只补一次。
- **UI 扩展**：`de` / `fr` / `es` 文本通常更长，标签要预留扩展空间，避免截断（如 `pf_avg_cost` 的德语 “Durchschnittlicher Einstandskurs”）。
- `ja` / `ko` / `zh` / `zh-TW` 不套用英文大小写与词间距规则。
- 语义层级：`aria-label` / `title` / Tooltip / 错误 `details` / 主提示各有分工；主提示简明，诊断细节留在 Details。
- 插值统一命名参数（`{count}`、`{name}`、`{value}`），所有语言参数集合一致。
- **禁止用显示文案做业务状态码或逻辑判断**：判断用稳定 `error` / `message_code` / 枚举值，不要用本地化后的可见文本。

## 13. 翻译与审查工作流

新增或修改某术语翻译时：

1. 确认 `concept_id` 与产品定义（§6 语义表）。
2. 核对真实代码上下文（`uiText.ts` / `locales/` 源文案与实际使用页面）。
3. 先稳定 `zh` / `en` 权威表达。
4. 用权威来源核对市场特有概念（§2 决策顺序）。
5. 生成其它语言候选（可参考 `translations/*.ts` 现有基线，但注意 §7 漂移）。
6. 进行母语与金融语义审校，重点排查 §7、§10 的风险点。
7. 检查 UI 长度、插值参数、可访问性文案与 report/UI language 边界。
8. 运行 i18n 资源、测试与构建（§15）。
9. 记录仍待确认的术语，不静默猜测。

## 14. Reviewer Checklist

可直接复制到 PR / review：

```text
[ ] 与真实产品语义一致（对照 concept_id 与源文案）
[ ] 使用了正确的市场与语言上下文
[ ] 未把信息性信号/评分/置信度误导为投资保证或指令
[ ] 正确区分 UI language 与 report language（report 仅 zh/en/ko）
[ ] 未翻译 contract value（error/message_code/枚举/模型 ID/URL/路由/字段名）
[ ] 保留全部插值参数，且各语言参数集合一致
[ ] 适配 UI 空间（de/fr/es 扩展）与辅助技术（aria/title/tooltip）
[ ] 已完成母语金融审校，或在 PR 明确记录缺口（§7）
[ ] 已核对 §10 风险禁止表达
[ ] 同步相关文档与 changelog（§15）
[ ] 运行了适用验证（i18n:resources / test:i18n / 必要时 build）
```

## 15. 文档组织原则与维护

- 本文档是十语言金融术语的**单一治理源**，不再创建十份完整指导文档。
- 术语表按领域拆分，语义表与翻译矩阵共用同一组 `concept_id` 且顺序一致；翻译矩阵列顺序固定为 `en` `zh` `zh-TW` `ja` `ko` `de` `es` `ms` `fr` `id`。
- 每个概念都给出产品定义，不只列翻译词。
- 使用稳定的仓库相对链接，禁止提交本机绝对路径。
- 不在 README 塞入完整术语表；README 只在首页级定位变化时更新。
- 不把未审校术语描述为“已验证”或“官方翻译”。

维护与验证（改动本文档或后续翻译时）：

```bash
cd apps/dsa-web
npm run i18n:resources   # 校验源 key/源文案与八个新增语言资源
npm run i18n:high-risk   # 校验高风险语义范围、证据状态、code/display 边界与快照
npm run test:i18n        # 十语言 key/空值/插值/NFC/零宽字符/重复 key + 硬编码扫描
# 依赖就绪时可再执行：
npm run lint
npm run test
npm run build
```

> 仅修改本文档时不会改变运行时资源；I18N-01 及后续翻译 PR 同时修改 bundle 时，必须执行上述三项校验。自动化通过仍不能替代母语金融审校。

## 16. 相关文档

- [Web 国际化开发约定](web-i18n.md) / [Web Internationalization Conventions](web-i18n_EN.md)
- [High-risk i18n semantic audit](high-risk-i18n-audit.md)
- [DecisionSignal 决策信号专题](decision-signals.md)
- [实时告警中心](alerts.md)
- [文档中心索引](INDEX.md)
- [更新日志](CHANGELOG.md)
- 源码锚点：[`i18n/uiLanguages.ts`](../apps/dsa-web/src/i18n/uiLanguages.ts) · [`i18n/uiText.ts`](../apps/dsa-web/src/i18n/uiText.ts) · [`i18n/translations/`](../apps/dsa-web/src/i18n/translations/) · [`locales/`](../apps/dsa-web/src/locales/) · [`utils/uiLocale.ts`](../apps/dsa-web/src/utils/uiLocale.ts) · [`utils/reportLanguage.ts`](../apps/dsa-web/src/utils/reportLanguage.ts)
