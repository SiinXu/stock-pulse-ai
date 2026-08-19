// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  formatDataQualityLevel,
  formatDataQualityLimitation,
} from '../dataQualityFormat/analysis';
import { formatAlertTriggerStatus } from '../dataQualityFormat/alerts';
import {
  formatDataQualityStatus,
  formatPortfolioStressQualityCell,
} from '../dataQualityFormat/portfolio';

describe('formatDataQualityStatus', () => {
  it('localizes known portfolio data-quality and status codes', () => {
    expect(formatDataQualityStatus('ok', 'zh')).toBe('正常');
    expect(formatDataQualityStatus('partial', 'zh')).toBe('部分可用');
    expect(formatDataQualityStatus('unavailable', 'zh')).toBe('不可用');
    expect(formatDataQualityStatus('ok', 'en')).toBe('OK');
    expect(formatDataQualityStatus('partial', 'en')).toBe('Partial');
    expect(formatDataQualityStatus('empty_portfolio', 'en')).toBe('Empty portfolio');
    expect(formatDataQualityStatus('insufficient_history', 'en')).toBe('Insufficient history');
    expect(formatDataQualityStatus('partial', 'ko')).toBe('부분 가능');
    expect(formatDataQualityStatus('ok', 'zh-TW')).toBe('正常');
    expect(formatDataQualityStatus('ok', 'ja')).toBe('正常');
    expect(formatDataQualityStatus('partial', 'fr')).toBe('Partiel');
  });

  it('uses an honest unknown fallback that keeps the raw code', () => {
    expect(formatDataQualityStatus(null, 'en')).toBe('Unknown status');
    expect(formatDataQualityStatus('', 'zh')).toBe('未知状态');
    expect(formatDataQualityStatus('mystery_code', 'en')).toBe('Unknown status (mystery_code)');
    expect(formatDataQualityStatus('mystery_code', 'zh')).toBe('未知状态 (mystery_code)');
    expect(formatDataQualityStatus('weird_quality', 'zh-TW')).toBe('未知狀態 (weird_quality)');
    expect(formatDataQualityStatus('weird_quality', 'ko')).toBe('알 수 없는 상태 (weird_quality)');
    expect(formatDataQualityStatus('weird_quality', 'ja')).toBe('不明な状態 (weird_quality)');
    expect(formatDataQualityStatus('weird_quality', 'fr')).toBe('Statut inconnu (weird_quality)');
    expect(formatDataQualityStatus('usable', 'zh')).toBe('未知状态 (usable)');
  });
});

describe('formatDataQualityLevel', () => {
  it('localizes known AnalysisContextPack quality levels', () => {
    expect(formatDataQualityLevel('good', 'zh')).toBe('良好');
    expect(formatDataQualityLevel('usable', 'zh')).toBe('可用');
    expect(formatDataQualityLevel('limited', 'zh')).toBe('受限');
    expect(formatDataQualityLevel('poor', 'zh')).toBe('较差');
    expect(formatDataQualityLevel('good', 'en')).toBe('Good');
    expect(formatDataQualityLevel('usable', 'en')).toBe('Usable');
    expect(formatDataQualityLevel('limited', 'en')).toBe('Limited');
    expect(formatDataQualityLevel('poor', 'en')).toBe('Poor');
    expect(formatDataQualityLevel('usable', 'ko')).toBe('사용 가능');
    expect(formatDataQualityLevel('usable', 'zh-TW')).toBe('可用');
    expect(formatDataQualityLevel('usable', 'ja')).toBe('Usable');
  });

  it('keeps unknown levels visible instead of inventing a mapped label', () => {
    expect(formatDataQualityLevel(null, 'en')).toBeNull();
    expect(formatDataQualityLevel('', 'zh')).toBeNull();
    expect(formatDataQualityLevel('not_a_real_level', 'en')).toBe('not_a_real_level');
    expect(formatDataQualityLevel('not_a_real_level', 'zh')).toBe('not_a_real_level');
  });
});

describe('formatDataQualityLimitation', () => {
  it('reuses existing block and status labels', () => {
    expect(formatDataQualityLimitation('fundamentals: fetch_failed', 'zh')).toBe('基本面：抓取失败');
    expect(formatDataQualityLimitation('fundamentals: fetch_failed', 'en')).toBe('fundamentals: Fetch failed');
    expect(formatDataQualityLimitation('news: missing', 'en')).toBe('news: Missing');
  });

  it('leaves unrecognized fragments visible', () => {
    expect(formatDataQualityLimitation('custom_block: custom_status', 'en')).toBe('custom_block: custom_status');
    expect(formatDataQualityLimitation('plain prose limitation', 'zh')).toBe('plain prose limitation');
  });
});

describe('formatAlertTriggerStatus', () => {
  it('localizes known trigger statuses', () => {
    expect(formatAlertTriggerStatus('triggered', 'zh')).toBe('已触发');
    expect(formatAlertTriggerStatus('skipped', 'zh')).toBe('已跳过');
    expect(formatAlertTriggerStatus('degraded', 'zh')).toBe('降级');
    expect(formatAlertTriggerStatus('failed', 'zh')).toBe('失败');
    expect(formatAlertTriggerStatus('triggered', 'en')).toBe('Triggered');
    expect(formatAlertTriggerStatus('skipped', 'en')).toBe('Skipped');
    expect(formatAlertTriggerStatus('degraded', 'en')).toBe('Degraded');
    expect(formatAlertTriggerStatus('failed', 'en')).toBe('Failed');
    expect(formatAlertTriggerStatus('triggered', 'zh-TW')).toBe('已觸發');
    expect(formatAlertTriggerStatus('triggered', 'ko')).toBe('트리거');
    expect(formatAlertTriggerStatus('triggered', 'ja')).toBe('トリガー');
    expect(formatAlertTriggerStatus('triggered', 'fr')).toBe('Déclenché');
  });

  it('keeps unknown trigger statuses visible', () => {
    expect(formatAlertTriggerStatus(null, 'en')).toBe('--');
    expect(formatAlertTriggerStatus('queued', 'en')).toBe('Unknown status (queued)');
    expect(formatAlertTriggerStatus('queued', 'zh')).toBe('未知状态 (queued)');
    expect(formatAlertTriggerStatus('queued', 'ko')).toBe('알 수 없는 상태 (queued)');
    expect(formatAlertTriggerStatus('queued', 'ja')).toBe('不明な状態 (queued)');
  });
});

describe('formatPortfolioStressQualityCell', () => {
  it('joins localized quality, stale, and limitation labels', () => {
    expect(formatPortfolioStressQualityCell({
      dataQuality: 'partial',
      priceStale: true,
      limitations: ['realtime_quote_best_effort'],
    }, 'en', 'Stale')).toBe('Partial · Stale · Realtime quotes are best-effort');

    expect(formatPortfolioStressQualityCell({
      dataQuality: 'ok',
      priceStale: false,
      limitations: [],
    }, 'zh', '过期')).toBe('正常');

    expect(formatPortfolioStressQualityCell({
      dataQuality: 'ok',
      priceStale: false,
      limitations: ['realtime_quote_best_effort'],
    }, 'ko', '만료')).toContain('정상');
  });

  it('keeps unknown quality and limitation codes visible', () => {
    expect(formatPortfolioStressQualityCell({
      dataQuality: 'weird_quality',
      priceStale: false,
      limitations: ['brand_new_limitation'],
    }, 'en', 'Stale')).toBe('Unknown status (weird_quality) · Unknown code (brand_new_limitation)');

    expect(formatPortfolioStressQualityCell({
      dataQuality: 'weird_quality',
      priceStale: false,
      limitations: ['brand_new_limitation'],
    }, 'ja', 'Stale')).toBe('不明な状態 (weird_quality) · 不明なコード（brand_new_limitation）');
  });
});
