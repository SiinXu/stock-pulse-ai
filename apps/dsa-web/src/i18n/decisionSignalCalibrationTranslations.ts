// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Shared long-form locale copy for decision-signal calibration. */
export const DECISION_SIGNAL_CALIBRATION_TRANSLATIONS = {
  de: {
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationInsufficientNotice": "Nur Anzahlen; keine Quoten.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationThreshold": "Quoten ab {count} Abschlüssen je Gruppe.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationDescription": "Nach Zeit, Markt und Signal; eigener Schwellenwert je Gruppe.",
    "i18n.uiText.UI_TEXT.decisionSignals.statsInsufficientNotice": "Unter {count}: nur Anzahlen.",
    "i18n.uiText.UI_TEXT.decisionSignals.researchPositionBody": "Historische Treffer: keine Prognose, Garantie oder Beratung.",
  },
  es: {
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationInsufficientNotice": "Muestra insuficiente: solo se muestran recuentos; las tasas permanecen ocultas.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationThreshold": "Cada grupo necesita al menos {count} muestras completadas antes de publicar las tasas de acierto.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationDescription": "Examina la calidad del proceso por período, mercado y tipo de señal. Cada grupo se habilita por separado; un grupo superior suficiente no desbloquea un subgrupo pequeño.",
    "i18n.uiText.UI_TEXT.decisionSignals.statsInsufficientNotice": "Las muestras completadas no alcanzan el umbral de publicación ({count}). Los recuentos siguen visibles; las tasas no se publican.",
    "i18n.uiText.UI_TEXT.decisionSignals.researchPositionBody": "Esta página muestra aciertos y calibración posteriores para evaluar la calidad del proceso de análisis. Las tasas de acierto solo describen la consistencia histórica; no predicen rentabilidades futuras ni son garantía o recomendación de inversión.",
  },
  fr: {
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationInsufficientNotice": "Comptes seuls.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationThreshold": "Seuil: {count}/groupe.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationDescription": "Seuil indépendant par période, marché et signal.",
    "i18n.uiText.UI_TEXT.decisionSignals.statsInsufficientNotice": "<{count}: comptes.",
    "i18n.uiText.UI_TEXT.decisionSignals.researchPositionBody": "Taux passés: ni prévision, garantie ou conseil.",
  },
  id: {
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationInsufficientNotice": "Hanya hitungan; tingkat disembunyikan.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationThreshold": "Tingkat tampil mulai {count} hasil per kelompok.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationDescription": "Menurut waktu, pasar, dan sinyal; ambang terpisah tiap kelompok.",
    "i18n.uiText.UI_TEXT.decisionSignals.statsInsufficientNotice": "Di bawah {count}: hanya hitungan.",
    "i18n.uiText.UI_TEXT.decisionSignals.researchPositionBody": "Tingkat historis; bukan prediksi, jaminan, atau saran investasi.",
  },
  ja: {
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationInsufficientNotice": "件数のみ。率は非公開。",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationThreshold": "各グループ{count}件から率を公開。",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationDescription": "期間・市場・種別別。各グループを個別判定。",
    "i18n.uiText.UI_TEXT.decisionSignals.statsInsufficientNotice": "{count}件未満：件数のみ。",
    "i18n.uiText.UI_TEXT.decisionSignals.researchPositionBody": "過去の的中率であり、将来収益の予測・保証・投資助言ではありません。",
  },
  ko: {
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationInsufficientNotice": "건수만 표시; 비율 비공개.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationThreshold": "그룹당 {count}건부터 공개.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationDescription": "기간·시장·신호 그룹별 독립 판정.",
    "i18n.uiText.UI_TEXT.decisionSignals.statsInsufficientNotice": "{count}건 미만: 건수만 표시.",
    "i18n.uiText.UI_TEXT.decisionSignals.researchPositionBody": "과거 적중률은 수익 예측·보장·투자 조언 아님.",
  },
  ms: {
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationInsufficientNotice": "Kiraan sahaja; kadar disembunyikan.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationThreshold": "Kadar diterbitkan mulai {count} hasil setiap kumpulan.",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationDescription": "Mengikut masa, pasaran dan isyarat; ambang berasingan setiap kumpulan.",
    "i18n.uiText.UI_TEXT.decisionSignals.statsInsufficientNotice": "Di bawah {count}: kiraan sahaja.",
    "i18n.uiText.UI_TEXT.decisionSignals.researchPositionBody": "Kadar sejarah; bukan ramalan, jaminan atau nasihat pelaburan.",
  },
  "zh-TW": {
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationInsufficientNotice": "僅計數，不公佈比率。",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationThreshold": "每組{count}筆起公佈。",
    "i18n.uiText.UI_TEXT.decisionSignals.calibrationDescription": "各時間、市場、訊號組獨立計閾。",
    "i18n.uiText.UI_TEXT.decisionSignals.statsInsufficientNotice": "未達{count}筆：僅計數。",
    "i18n.uiText.UI_TEXT.decisionSignals.researchPositionBody": "歷史命中率非收益預測、保證或建議。",
  },
} as const;
