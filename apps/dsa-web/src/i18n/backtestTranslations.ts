// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Shared localized copy for the backtest methodology and execution-cost settings. */
export const BACKTEST_TRANSLATIONS = {
  de: {
    "locales.backtest.BACKTEST_TEXT.methodologyDisclaimer": "Nur historische Simulation zur Forschung — kein Renditeversprechen und keine Live-Fills. Look-ahead-Schutz, Survivorship-Grenzen (nur analysiertes Universum) und explizite Gebühren/Slippage sind ausgewiesen. Prozentuale Renditen sind währungsagnostisch; absolute Preise werden nie währungsübergreifend summiert.",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_COMMISSION_BPS": "Backtest-Provision (Bp/Seite)",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_SLIPPAGE_BPS": "Backtest-Slippage (Bp/Seite)",
  },
  es: {
    "locales.backtest.BACKTEST_TEXT.methodologyDisclaimer": "Solo simulación histórica para investigación: no es promesa de rentabilidad ni fills reales. Se declaran la protección look-ahead, los límites de supervivencia (solo universo analizado) y la comisión/deslizamiento explícitos. Los retornos porcentuales son agnósticos a la moneda; los precios absolutos no se suman entre monedas.",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_COMMISSION_BPS": "Comisión de backtest (pb/lado)",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_SLIPPAGE_BPS": "Deslizamiento de backtest (pb/lado)",
  },
  fr: {
    "locales.backtest.BACKTEST_TEXT.methodologyDisclaimer": "Simulation historique pour la recherche uniquement — pas une promesse de rendement ni des fills réels. Protection anti look-ahead, limites de survivance (univers analysé uniquement) et commission/slippage explicites sont indiqués. Les rendements en pourcentage sont indépendants de la devise ; les prix absolus ne sont jamais additionnés entre devises.",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_COMMISSION_BPS": "Commission de backtest (pb/côté)",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_SLIPPAGE_BPS": "Slippage de backtest (pb/côté)",
  },
  id: {
    "locales.backtest.BACKTEST_TEXT.methodologyDisclaimer": "Hanya simulasi historis untuk riset — bukan janji imbal hasil dan bukan fill live. Perlindungan look-ahead, batas survivorship (hanya universe yang dianalisis), serta komisi/slippage eksplisit diungkapkan. Imbal hasil persentase netral terhadap mata uang; harga absolut tidak pernah dijumlah lintas mata uang.",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_COMMISSION_BPS": "Komisi backtest (bp/sisi)",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_SLIPPAGE_BPS": "Slippage backtest (bp/sisi)",
  },
  ja: {
    "locales.backtest.BACKTEST_TEXT.methodologyDisclaimer": "研究用の履歴シミュレーションのみであり、将来リターンの約束でも実約定でもありません。先読み防止、生存者バイアスの制限（分析済みユニバースのみ）、明示的な手数料/スリッページを開示しています。パーセントリターンは通貨非依存です。絶対価格は通貨をまたいで合算しません。",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_COMMISSION_BPS": "バックテスト手数料（bp/片側）",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_SLIPPAGE_BPS": "バックテストスリッページ（bp/片側）",
  },
  ko: {
    "locales.backtest.BACKTEST_TEXT.methodologyDisclaimer": "연구용 역사 시뮬레이션일 뿐이며 수익 약속이나 실체결이 아닙니다. 선견 편향 방지, 생존자 편향 한계(분석된 유니버스만), 명시적 수수료/슬리피지를 고지합니다. 백분율 수익률은 통화에 중립적이며, 절대 가격은 통화 간 합산하지 않습니다.",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_COMMISSION_BPS": "백테스트 수수료(bp/편측)",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_SLIPPAGE_BPS": "백테스트 슬리피지(bp/편측)",
  },
  ms: {
    "locales.backtest.BACKTEST_TEXT.methodologyDisclaimer": "Simulasi sejarah untuk penyelidikan sahaja — bukan janji pulangan dan bukan fill langsung. Perlindungan look-ahead, had survivorship (hanya alam semesta dianalisis) serta komisen/gelinciran eksplisit didedahkan. Pulangan peratusan agnostik mata wang; harga mutlak tidak pernah dijumlah merentas mata wang.",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_COMMISSION_BPS": "Komisen backtest (bp/sisi)",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_SLIPPAGE_BPS": "Gelinciran backtest (bp/sisi)",
  },
  "zh-TW": {
    "locales.backtest.BACKTEST_TEXT.methodologyDisclaimer": "历史模拟研究用途，不是收益承诺，也不是真实成交。已声明前视偏差防护、幸存者偏差（仅本机已分析标的）与显式费用/滑点模型；百分比收益跨币种可比，绝对价格不会跨币种直接加总。",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_COMMISSION_BPS": "回测佣金（基点/单边）",
    "utils.systemConfigI18n.fieldTitleMaps.BACKTEST_SLIPPAGE_BPS": "回测滑点（基点/单边）",
  },
} as const;
