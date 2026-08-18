// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  FIELD_TRUST_TEXT,
  fieldTrustGapMessage,
  fieldTrustStatusMessage,
} from '../fieldTrust';

describe('field-trust localized copy', () => {
  it('keeps zh and en inventories in parity', () => {
    expect(Object.keys(FIELD_TRUST_TEXT.zh).sort()).toEqual(Object.keys(FIELD_TRUST_TEXT.en).sort());
    expect(FIELD_TRUST_TEXT['zh-TW']).toBe(FIELD_TRUST_TEXT.zh);
    expect(FIELD_TRUST_TEXT.ja).toBe(FIELD_TRUST_TEXT.en);
  });

  it('localizes known status and gap codes in zh and English', () => {
    const zh = FIELD_TRUST_TEXT.zh;
    const en = FIELD_TRUST_TEXT.en;
    expect(fieldTrustStatusMessage(zh, 'degraded')).toContain('过期、冲突、未归因或数据源失败');
    expect(fieldTrustStatusMessage(en, 'degraded')).toMatch(/stale, conflicting, unattributed/i);
    expect(fieldTrustStatusMessage(zh, 'unavailable')).toContain('所有数据源都未能返回行情');
    expect(fieldTrustGapMessage(zh, { code: 'conflict', field: 'price', detail: 'providers disagreed' })).toContain(
      '数据源对该字段意见不一致',
    );
    expect(fieldTrustGapMessage(en, { code: 'conflict', field: 'price', detail: 'providers disagreed' })).toMatch(
      /providers disagreed/i,
    );
    expect(
      fieldTrustGapMessage(zh, {
        code: 'provider_unavailable',
        detail: 'longbridge:unavailable',
      }),
    ).toContain('数据源不可用');
    expect(
      fieldTrustGapMessage(en, {
        code: 'provider_unavailable',
        detail: 'longbridge:unavailable',
      }),
    ).toMatch(/provider unavailable/i);
  });

  it('uses a safe fallback for unknown future gap codes instead of backend English', () => {
    const zh = fieldTrustGapMessage(FIELD_TRUST_TEXT.zh, {
      code: 'future_gap_code',
      detail: 'Totally English backend sentence that must not leak into zh',
    });
    expect(zh).toContain('future_gap_code');
    expect(zh).not.toContain('Totally English backend sentence');
    expect(
      fieldTrustGapMessage(FIELD_TRUST_TEXT.en, { code: 'future_gap_code', detail: 'backend english' }),
    ).toContain('future_gap_code');
  });
});
