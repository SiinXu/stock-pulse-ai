// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiTranslationKey } from './translations/en';

type FutuImportKey = Extract<
  UiTranslationKey,
  `locales.portfolioFutuImport.PORTFOLIO_FUTU_IMPORT_TEXT.${string}`
>;

const PREFIX = 'locales.portfolioFutuImport.PORTFOLIO_FUTU_IMPORT_TEXT.';
function withPrefix(values: Record<string, string>): Record<FutuImportKey, string> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [`${PREFIX}${key}`, value]),
  ) as Record<FutuImportKey, string>;
}

export const PORTFOLIO_FUTU_IMPORT_TRANSLATIONS_WEST = {
  de: withPrefix({
    openImport: 'Positionen importieren',
    sourceLabel: 'Importquelle', fileSource: 'Brokerdatei', futuSource: 'Futu-OpenD-Verbindung', fileDescription: 'Wählen Sie ein Brokerformat und laden Sie CSV/Excel hoch oder fügen Sie Tabellentext ein.', futuDescription: 'Liest echte Long-Aktienpositionen aus dem konfigurierten Futu OpenD. Die Vorschau schreibt keine Daten und führt keine Trades aus.', previewStep: 'Verbinden und prüfen', futuAsOf: 'Synthetisches Handelsdatum', futuAsOfHint: 'Optional; leer lassen, um das Backend-Datum zu verwenden. Nach einer Änderung ist eine neue Vorschau nötig.', preview: 'Erneut prüfen', previewing: 'OpenD wird gelesen…', previewResult: 'Vorschau der Futu-Positionen', previewEmpty: 'OpenD hat keine importierbaren echten Long-Aktienpositionen geliefert.', previewRequired: 'Prüfen Sie zuerst die Futu-Positionen, bevor Sie den Import bestätigen.',
  }),
  es: withPrefix({
    openImport: 'Importar posiciones',
    sourceLabel: 'Origen de importación', fileSource: 'Archivo del bróker', futuSource: 'Conexión Futu OpenD', fileDescription: 'Elige el formato del bróker y sube CSV/Excel o pega texto tabular.', futuDescription: 'Lee posiciones largas reales de acciones desde Futu OpenD configurado. La vista previa no escribe datos ni ejecuta operaciones.', previewStep: 'Conectar y previsualizar', futuAsOf: 'Fecha sintética de operación', futuAsOfHint: 'Opcional; déjalo vacío para usar la fecha del servidor. Un cambio exige otra vista previa.', preview: 'Previsualizar de nuevo', previewing: 'Leyendo OpenD…', previewResult: 'Vista previa de posiciones Futu', previewEmpty: 'OpenD no devolvió posiciones largas reales aptas para importar.', previewRequired: 'Previsualiza correctamente las posiciones Futu antes de confirmar la importación.',
  }),
  fr: withPrefix({
    openImport: 'Importer des positions',
    sourceLabel: 'Source d’importation', fileSource: 'Fichier du courtier', futuSource: 'Connexion Futu OpenD', fileDescription: 'Choisissez le format du courtier puis chargez un CSV/Excel ou collez du texte tabulaire.', futuDescription: 'Lit les positions longues réelles en actions depuis Futu OpenD configuré. L’aperçu n’écrit aucune donnée et n’exécute aucun ordre.', previewStep: 'Connecter et prévisualiser', futuAsOf: 'Date de transaction synthétique', futuAsOfHint: 'Facultatif ; laissez vide pour utiliser la date du serveur. Toute modification exige un nouvel aperçu.', preview: 'Prévisualiser à nouveau', previewing: 'Lecture d’OpenD…', previewResult: 'Aperçu des positions Futu', previewEmpty: 'OpenD n’a renvoyé aucune position longue réelle admissible à l’importation.', previewRequired: 'Prévisualisez correctement les positions Futu avant de confirmer l’importation.',
  }),
  id: withPrefix({
    openImport: 'Impor posisi',
    sourceLabel: 'Sumber impor', fileSource: 'Berkas broker', futuSource: 'Koneksi Futu OpenD', fileDescription: 'Pilih format broker lalu unggah CSV/Excel atau tempel teks tabel.', futuDescription: 'Membaca posisi saham long nyata dari Futu OpenD yang dikonfigurasi. Pratinjau tidak menulis data atau mengeksekusi transaksi.', previewStep: 'Hubungkan dan pratinjau', futuAsOf: 'Tanggal transaksi sintetis', futuAsOfHint: 'Opsional; kosongkan untuk memakai tanggal backend. Perubahan memerlukan pratinjau baru.', preview: 'Pratinjau lagi', previewing: 'Membaca OpenD…', previewResult: 'Pratinjau posisi Futu', previewEmpty: 'OpenD tidak mengembalikan posisi saham long nyata yang memenuhi syarat impor.', previewRequired: 'Pratinjau posisi Futu dengan sukses sebelum mengonfirmasi impor.',
  }),
} satisfies Record<string, Record<FutuImportKey, string>>;
