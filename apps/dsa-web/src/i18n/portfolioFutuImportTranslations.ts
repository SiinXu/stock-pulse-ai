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

export const PORTFOLIO_FUTU_IMPORT_TRANSLATIONS = {
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
  ja: withPrefix({
    openImport: 'ポジションをインポート',
    sourceLabel: 'インポート元', fileSource: '証券会社ファイル', futuSource: 'Futu OpenD 接続', fileDescription: '証券会社の形式を選び、CSV/Excel をアップロードするか表形式テキストを貼り付けます。', futuDescription: '設定済みの Futu OpenD から実口座の買い持ち株式を読み取ります。プレビューでは書き込みも取引実行も行いません。', previewStep: '接続してプレビュー', futuAsOf: '合成約定日', futuAsOfHint: '任意。空欄ではバックエンドの日付を使います。変更後は再プレビューが必要です。', preview: '再プレビュー', previewing: 'OpenD を読み取り中…', previewResult: 'Futu ポジションのプレビュー', previewEmpty: 'インポート対象となる実口座の買い持ち株式が OpenD から返されませんでした。', previewRequired: 'インポートを確定する前に Futu ポジションを正常にプレビューしてください。',
  }),
  ko: withPrefix({
    openImport: '포지션 가져오기',
    sourceLabel: '가져오기 원본', fileSource: '증권사 파일', futuSource: 'Futu OpenD 연결', fileDescription: '증권사 형식을 선택한 뒤 CSV/Excel을 업로드하거나 표 텍스트를 붙여 넣으세요.', futuDescription: '설정된 Futu OpenD에서 실제 롱 주식 포지션을 읽습니다. 미리보기는 데이터를 쓰거나 거래를 실행하지 않습니다.', previewStep: '연결 및 미리보기', futuAsOf: '합성 거래일', futuAsOfHint: '선택 사항입니다. 비워 두면 백엔드 날짜를 사용하며 변경 후 다시 미리봐야 합니다.', preview: '다시 미리보기', previewing: 'OpenD 읽는 중…', previewResult: 'Futu 포지션 미리보기', previewEmpty: 'OpenD에서 가져올 수 있는 실제 롱 주식 포지션을 찾지 못했습니다.', previewRequired: '가져오기를 확정하기 전에 Futu 포지션을 먼저 미리보세요.',
  }),
  ms: withPrefix({
    openImport: 'Import pegangan',
    sourceLabel: 'Sumber import', fileSource: 'Fail broker', futuSource: 'Sambungan Futu OpenD', fileDescription: 'Pilih format broker kemudian muat naik CSV/Excel atau tampal teks jadual.', futuDescription: 'Membaca pegangan saham panjang sebenar daripada Futu OpenD yang dikonfigurasi. Pratonton tidak menulis data atau melaksanakan dagangan.', previewStep: 'Sambung dan pratonton', futuAsOf: 'Tarikh dagangan sintetik', futuAsOfHint: 'Pilihan; biarkan kosong untuk tarikh backend. Perubahan memerlukan pratonton baharu.', preview: 'Pratonton semula', previewing: 'Membaca OpenD…', previewResult: 'Pratonton pegangan Futu', previewEmpty: 'OpenD tidak mengembalikan pegangan saham panjang sebenar yang layak diimport.', previewRequired: 'Pratonton pegangan Futu dengan jayanya sebelum mengesahkan import.',
  }),
  'zh-TW': withPrefix({
    openImport: '匯入持倉',
    sourceLabel: '匯入來源', fileSource: '券商檔案', futuSource: 'Futu OpenD 連線', fileDescription: '選擇券商格式後上傳 CSV/Excel，或貼上表格文字。', futuDescription: '從已設定的 Futu OpenD 讀取真實多頭正股持倉。預覽不會寫入資料，也不會執行交易。', previewStep: '連線並預覽', futuAsOf: '合成成交日期', futuAsOfHint: '可選；留空使用後端目前日期。修改日期後必須重新預覽。', preview: '重新預覽', previewing: '正在讀取 OpenD…', previewResult: 'Futu 持倉預覽', previewEmpty: 'OpenD 目前沒有符合匯入條件的真實多頭正股持倉。', previewRequired: '必須先成功預覽 Futu 持倉，才能確認匯入。',
  }),
} satisfies Record<string, Record<FutuImportKey, string>>;
