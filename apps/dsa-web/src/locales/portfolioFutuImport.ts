// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';

export const PORTFOLIO_FUTU_IMPORT_TEXT = createUiLanguageRecord(
  'locales.portfolioFutuImport.PORTFOLIO_FUTU_IMPORT_TEXT',
  {
    zh: {
      openImport: '导入持仓',
      sourceLabel: '导入来源',
      fileSource: '券商文件',
      futuSource: 'Futu OpenD',
      fileDescription: '选择券商格式后上传 CSV/Excel，或粘贴表格文本。',
      futuDescription: '从已配置的 Futu OpenD 读取真实多头正股持仓。预览不会写入，也不会执行交易。',
      previewStep: '连接并预览',
      futuAsOf: '合成成交日期',
      futuAsOfHint: '可选；留空使用后端当前日期。修改日期后必须重新预览。',
      preview: '重新预览',
      previewing: '正在读取 OpenD…',
      previewResult: 'Futu 持仓预览',
      previewEmpty: 'OpenD 当前没有符合导入条件的真实多头正股持仓，无法提交。',
      previewRequired: '必须先成功预览 Futu 持仓，才能提交导入。',
    },
    en: {
      openImport: 'Import positions',
      sourceLabel: 'Import source',
      fileSource: 'Broker file',
      futuSource: 'Futu OpenD',
      fileDescription: 'Choose a broker format, then upload CSV/Excel or paste table text.',
      futuDescription: 'Read live long stock positions from the configured Futu OpenD. Previewing never writes data or executes trades.',
      previewStep: 'Connect and preview',
      futuAsOf: 'Synthetic trade date',
      futuAsOfHint: 'Optional; leave blank to use the backend date. Changing it requires a fresh preview.',
      preview: 'Preview again',
      previewing: 'Reading OpenD…',
      previewResult: 'Futu position preview',
      previewEmpty: 'OpenD returned no eligible live long stock positions, so there is nothing to commit.',
      previewRequired: 'Preview Futu positions successfully before committing the import.',
    },
  } as const,
);
