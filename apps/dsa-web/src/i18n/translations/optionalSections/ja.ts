// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

// Isolated from core locale-{locale} chunks so optional-section honesty
// copy is not billed to locale-ja-family (Refs #188 / #1375 cap).
export const OPTIONAL_SECTION_HONESTY_TRANSLATIONS = {
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalPreviewEmpty": 'セクションは生成されましたが、項目はありません',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionAbsent": 'セクション未生成',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionCatalysts": '触媒',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionMultiAgent": 'マルチエージェント',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionPresent": '生成済み（{count}）',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionStructuredRisk": '構造化リスク',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsDescription": 'マルチエージェント、構造化リスク、触媒セクションは任意です。欠落は明示され、空の内容が一致しているとは扱いません。T17 エンジン差分を補完し、置き換えません。',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsTitle": '任意セクションの明示',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBaseMissing": '基準実行はこのセクションを生成していません',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBothMissing": 'どちらの実行もこのセクションを生成していません',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentDifferent": '両方の実行にこのセクションがあり、内容が異なります',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentIdentical": '両方の実行にこのセクションがあり、内容は同じです',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusTargetMissing": '比較実行はこのセクションを生成していません',
};
