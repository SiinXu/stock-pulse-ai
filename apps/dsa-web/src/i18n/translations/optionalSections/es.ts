// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

// Isolated from core locale-{locale} chunks so optional-section honesty
// copy is not billed to locale-ja-family (Refs #188 / #1375 cap).
export const OPTIONAL_SECTION_HONESTY_TRANSLATIONS = {
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalPreviewEmpty": 'La sección se produjo, pero no tiene elementos',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionAbsent": 'Sección no producida',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionCatalysts": 'Catalizadores',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionMultiAgent": 'Multiagente',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionPresent": 'Producida ({count})',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionStructuredRisk": 'Riesgo estructurado',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsDescription": 'Las secciones multiagente, de riesgo estructurado y de catalizadores son opcionales. La ausencia se etiqueta de forma explícita y no se trata como contenido vacío coincidente. Complementa el delta T17; no lo reemplaza.',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsTitle": 'Honestidad de secciones opcionales',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBaseMissing": 'La versión base no produjo esta sección',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBothMissing": 'Ninguna ejecución produjo esta sección',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentDifferent": 'Ambas ejecuciones incluyen esta sección y el contenido difiere',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentIdentical": 'Ambas ejecuciones incluyen esta sección con el mismo contenido',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusTargetMissing": 'La versión candidata no produjo esta sección',
};
