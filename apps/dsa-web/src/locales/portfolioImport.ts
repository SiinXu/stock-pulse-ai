// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiLanguage } from '../i18n/uiLanguages';

export const SOURCE_PORTFOLIO_IMPORT_TEXT = {
    zh: {
      actualWrite: '实际写入',
      brokerListEmpty: '券商列表为空，暂时无法导入 CSV。',
      brokerListUnavailable: '券商列表不可用，请刷新后重试。',
      chooseCsv: '选择 CSV / Excel',
      commitImport: '提交导入',
      csvCommitResult: 'CSV 提交结果',
      csvCommitSummary: '{mode}：写入 {inserted} 条，重复 {duplicates} 条，失败 {failed} 条。',
      csvDryResult: 'CSV 预演结果',
      csvFile: 'CSV / Excel 文件',
      csvParseResult: 'CSV 解析结果',
      csvParseSummary: '有效 {valid} 条，跳过 {skipped} 条，错误 {errors} 条。',
      openImport: '导入持仓',
      description: '选择 CSV / Excel、粘贴表格或 Futu OpenD，预览规范化记录并确认后再写入账户。',
      dryCheck: '预演检查',
      dryRun: '仅预演（不写入）',
      source: '导入来源',
      file: '文件或粘贴',
      futu: 'Futu OpenD',
      futuHelp: '从本机 Futu OpenD 读取实盘持仓。必须先预览；确认时若持仓已变化，提交会被拒绝并要求重新预览。',
      futuAsOf: '合成买入日期',
      futuAsOfHint: 'Futu 持仓会转换为该日期的合成买入记录。修改日期后必须重新预览。',
      preview: '预览持仓',
      previewing: '正在预览',
      previewRequired: '提交前必须完成与当前来源和日期匹配的预览。',
      snapshot: '已确认快照',
      parsing: '解析中...',
      parseFile: '解析文件',
      importWizardTitle: '导入持仓向导',
      importWizardStepsLabel: '导入步骤',
      importWizardStepUpload: '上传或粘贴',
      importWizardStepMapping: '字段映射',
      importWizardStepValidate: '校验结果',
      importWizardStepConfirm: '确认导入',
      importWizardFormatHelp: '选择券商表格格式。系统按该格式解析 CSV/XLSX 列含义，无需手工逐列映射。',
      importWizardPasteLabel: '或粘贴表格文本',
      importWizardPasteHint: '可直接粘贴 CSV 并在此修改错误行后重新解析；Excel 请下载失败行修正后重新上传。',
      importWizardMappingHelp: '以下为解析后的标准化字段预览（最多 50 行）。',
      importWizardMappingTitle: '字段映射预览',
      importWizardMappingEmpty: '暂无映射预览。请先解析表格，或返回上一步检查文件内容。',
      importWizardValidateHelp: '逐行校验结果。错误带行号与原因；修正粘贴内容或更换文件后可重试，无需整份流程重做。',
      importWizardRowErrors: '行级错误',
      importWizardNoErrors: '未发现解析错误，可以继续确认导入。',
      importWizardRetryHint: '坏数据已显式拒绝。请下载失败行修正后重新上传，或返回编辑粘贴内容后重新解析。',
      importWizardContinueEdit: '返回修正',
      importWizardConfirmHelp: '确认写入目标账户。可先预演再实际提交；部分成功时会明确展示写入、重复与失败条数。',
      importWizardPartialTitle: '部分导入成功',
      importWizardPartialHelp: '部分行已写入，失败行可下载修正后重试。已成功行依赖幂等键，重复提交不会产生重复台账。',
      importWizardFailedRowsTitle: '失败行（可下载修正）',
      importWizardFailedRowNumber: '行号',
      importWizardFailedRowCode: '原因代码',
      importWizardFailedRowReason: '拒绝原因',
      importWizardDownloadFailedRows: '下载失败行 CSV',
      importWizardNext: '下一步',
      importWizardBack: '上一步',
      importWizardDone: '完成',
    },
    en: {
      actualWrite: 'Committed',
      brokerListEmpty: 'The broker list is empty. Broker imports are unavailable.',
      brokerListUnavailable: 'The broker list is unavailable. Refresh and try again.',
      chooseCsv: 'Choose CSV / Excel',
      commitImport: 'Commit import',
      csvCommitResult: 'CSV commit result',
      csvCommitSummary: '{mode}: {inserted} inserted, {duplicates} duplicates, {failed} failed.',
      csvDryResult: 'CSV dry-run result',
      csvFile: 'CSV / Excel file',
      csvParseResult: 'CSV parse result',
      csvParseSummary: '{valid} valid, {skipped} skipped, {errors} errors.',
      openImport: 'Import positions',
      description: 'Choose CSV / Excel, pasted table data, or Futu OpenD; preview normalized records before confirming an account write.',
      dryCheck: 'Dry-run check',
      dryRun: 'Dry run (no writes)',
      source: 'Import source',
      file: 'File or paste',
      futu: 'Futu OpenD',
      futuHelp: 'Read real positions from the local Futu OpenD service. A preview is required; commit is rejected when positions changed after confirmation.',
      futuAsOf: 'Synthetic buy date',
      futuAsOfHint: 'Futu positions become synthetic buy records on this date. Changing it requires a new preview.',
      preview: 'Preview positions',
      previewing: 'Previewing',
      previewRequired: 'A preview matching the current source and date is required before commit.',
      snapshot: 'Confirmed snapshot',
      parsing: 'Parsing...',
      parseFile: 'Parse file',
      importWizardTitle: 'Import portfolio wizard',
      importWizardStepsLabel: 'Import steps',
      importWizardStepUpload: 'Upload or paste',
      importWizardStepMapping: 'Field mapping',
      importWizardStepValidate: 'Validation',
      importWizardStepConfirm: 'Confirm',
      importWizardFormatHelp: 'Select the broker spreadsheet format. The system maps CSV/XLSX columns from that format; no manual per-column mapping is required.',
      importWizardPasteLabel: 'Or paste table text',
      importWizardPasteHint: 'Paste CSV text and edit bad rows here, then re-parse. For Excel, download failed rows, fix them, and re-upload.',
      importWizardMappingHelp: 'Preview of normalized fields after parse (up to 50 rows).',
      importWizardMappingTitle: 'Field mapping preview',
      importWizardMappingEmpty: 'No mapping preview yet. Parse the spreadsheet, or go back and check the file content.',
      importWizardValidateHelp: 'Row-level validation. Errors include line numbers and reasons. Fix paste content or replace the file and retry without restarting the whole flow.',
      importWizardRowErrors: 'Row errors',
      importWizardNoErrors: 'No parse errors. You can continue to confirm the import.',
      importWizardRetryHint: 'Bad rows were rejected with reasons. Download failed rows to fix them, or return to edit the paste content and parse again.',
      importWizardContinueEdit: 'Edit source',
      importWizardConfirmHelp: 'Confirm writing into the selected account. Use dry-run first if needed. Partial success shows inserted, duplicate, and failed counts clearly.',
      importWizardPartialTitle: 'Partial import success',
      importWizardPartialHelp: 'Some rows were written; download failed rows to fix and retry. Successful rows stay idempotent and will not duplicate ledger entries.',
      importWizardFailedRowsTitle: 'Failed rows (download to fix)',
      importWizardFailedRowNumber: 'Row',
      importWizardFailedRowCode: 'Reason code',
      importWizardFailedRowReason: 'Rejection reason',
      importWizardDownloadFailedRows: 'Download failed rows CSV',
      importWizardNext: 'Next',
      importWizardBack: 'Back',
      importWizardDone: 'Done',
    },
} as const;

export type PortfolioImportText = Record<keyof typeof SOURCE_PORTFOLIO_IMPORT_TEXT.zh, string>;
type AdditionalLanguage = Exclude<UiLanguage, 'zh' | 'en'>;
type PortfolioImportTranslationModule = { portfolioImportText: PortfolioImportText };

const TRANSLATION_LOADERS = {
  de: () => import('./portfolioInsightsTranslations/de'),
  es: () => import('./portfolioInsightsTranslations/es'),
  fr: () => import('./portfolioInsightsTranslations/fr'),
  id: () => import('./portfolioInsightsTranslations/id'),
  ja: () => import('./portfolioInsightsTranslations/ja'),
  ko: () => import('./portfolioInsightsTranslations/ko'),
  ms: () => import('./portfolioInsightsTranslations/ms'),
  'zh-TW': () => import('./portfolioInsightsTranslations/zh-TW'),
} satisfies Record<AdditionalLanguage, () => Promise<PortfolioImportTranslationModule>>;

const translationCache = new Map<AdditionalLanguage, PortfolioImportText>();

export function getPortfolioImportText(language: UiLanguage): PortfolioImportText | null {
  if (language === 'zh' || language === 'en') return SOURCE_PORTFOLIO_IMPORT_TEXT[language];
  return translationCache.get(language) ?? null;
}

export async function loadPortfolioImportText(language: UiLanguage): Promise<PortfolioImportText> {
  if (language === 'zh' || language === 'en') return SOURCE_PORTFOLIO_IMPORT_TEXT[language];
  const cached = translationCache.get(language);
  if (cached) return cached;
  const translated = (await TRANSLATION_LOADERS[language]()).portfolioImportText;
  translationCache.set(language, translated);
  return translated;
}
