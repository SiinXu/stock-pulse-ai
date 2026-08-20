// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

// Isolated from core locale-{locale} chunks so optional-section honesty
// copy is not billed to locale-ja-family (Refs #188 / #1375 cap).
export const OPTIONAL_SECTION_HONESTY_TRANSLATIONS = {
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalPreviewEmpty": 'Section produite, mais sans éléments',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionAbsent": 'Section non produite',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionCatalysts": 'Catalyseurs',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionMultiAgent": 'Multi-agents',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionPresent": 'Produite ({count})',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionStructuredRisk": 'Risque structuré',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsDescription": 'Les sections multi-agents, risques structurés et catalyseurs sont facultatives. Une absence est indiquée explicitement et n’est pas traitée comme un contenu vide identique. Cela complète le delta T17 sans le remplacer.',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalSectionsTitle": 'Honnêteté des sections facultatives',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBaseMissing": 'La version de base n’a pas produit cette section',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusBothMissing": 'Aucune des deux exécutions n’a produit cette section',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentDifferent": 'Les deux exécutions incluent cette section, avec un contenu différent',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusPresentIdentical": 'Les deux exécutions incluent cette section avec le même contenu',
    "locales.reportVersionCompare.REPORT_VERSION_COMPARE_TEXT.optionalStatusTargetMissing": 'La version candidate n’a pas produit cette section',
};
