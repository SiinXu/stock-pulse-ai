// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

// Isolated from core locale-{locale} chunks so optional-section honesty
// copy is not billed to locale-ja-family (Refs #188 / #1375 cap).
export const OPTIONAL_SECTION_HONESTY_TRANSLATIONS = {
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalPreviewEmpty": 'Abschnitt erzeugt, aber ohne Einträge',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionAbsent": 'Abschnitt nicht erzeugt',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionCatalysts": 'Katalysatoren',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionMultiAgent": 'Multi-Agent',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionPresent": 'Erzeugt ({count})',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionStructuredRisk": 'Strukturiertes Risiko',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsDescription": 'Multi-Agent-, strukturierte Risiko- und Katalysatorabschnitte sind optional. Fehlende Abschnitte werden ausdrücklich gekennzeichnet und nicht als identischer Leerlauf behandelt. Dies ergänzt das T17-Delta und ersetzt es nicht.',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsTitle": 'Ehrlichkeit optionaler Abschnitte',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBaseMissing": 'Die Basisversion hat diesen Abschnitt nicht erzeugt',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBothMissing": 'Keine der beiden Läufe hat diesen Abschnitt erzeugt',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentDifferent": 'Beide Läufe enthalten diesen Abschnitt, die Inhalte unterscheiden sich',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentIdentical": 'Beide Läufe enthalten diesen Abschnitt mit gleichem Inhalt',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusTargetMissing": 'Die Vergleichsversion hat diesen Abschnitt nicht erzeugt',
};
