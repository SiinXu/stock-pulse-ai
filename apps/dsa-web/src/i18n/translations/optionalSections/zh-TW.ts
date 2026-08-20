// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

// Isolated from core locale-{locale} chunks so optional-section honesty
// copy is not billed to locale-ja-family (Refs #188 / #1375 cap).
export const OPTIONAL_SECTION_HONESTY_TRANSLATIONS = {
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalPreviewEmpty": '區塊已產出，但沒有條目',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionAbsent": '未產出該區塊',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionCatalysts": '催化',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionMultiAgent": '多智能體',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionPresent": '已產出（{count}）',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionStructuredRisk": '結構化風險',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsDescription": '多智能體、結構化風險與催化區塊是可選的。缺失會明確標出，不會被當成「兩邊都為空所以相同」。該項補充 T17 引擎差異，不替代它。',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsTitle": '可選區塊誠實對照',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBaseMissing": '基線未產出該區塊',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBothMissing": '兩次運行都未產出該區塊',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentDifferent": '兩邊都包含該區塊，內容不同',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentIdentical": '兩邊都包含該區塊，內容相同',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusTargetMissing": '對比版本未產出該區塊',
};
