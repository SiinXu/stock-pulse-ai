// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { getDiscoveryResultsEmptyKind } from '../discoveryEmptyState';

describe('getDiscoveryResultsEmptyKind', () => {
  it('returns null when candidates are present', () => {
    expect(getDiscoveryResultsEmptyKind({
      status: 'degraded',
      emptyReason: 'provider_unavailable',
      candidateCount: 1,
      candidates: [{ rank: 1, code: '000001', name: 'Demo', reason: '', raw: {} }],
    })).toBeNull();
  });

  it('classifies genuine empty, degraded, and unconfigured results differently', () => {
    expect(getDiscoveryResultsEmptyKind({
      status: 'empty',
      emptyReason: 'no_criteria_match',
      candidateCount: 0,
      candidates: [],
    })).toBe('no_hits');
    expect(getDiscoveryResultsEmptyKind({
      status: 'empty',
      emptyReason: 'no_ranked_candidates',
      candidateCount: 0,
      candidates: [],
    })).toBe('no_hits');
    expect(getDiscoveryResultsEmptyKind({
      status: 'degraded_empty',
      emptyReason: 'provider_unavailable',
      candidateCount: 0,
      candidates: [],
    })).toBe('source_unavailable');
    expect(getDiscoveryResultsEmptyKind({
      status: 'empty',
      emptyReason: 'provider_unavailable',
      candidateCount: 0,
      candidates: [],
    })).toBe('source_unavailable');
    expect(getDiscoveryResultsEmptyKind({
      status: 'empty',
      emptyReason: 'empty_universe',
      candidateCount: 0,
      candidates: [],
    })).toBe('unconfigured');
  });

  it('does not treat an unknown empty payload as source failure', () => {
    expect(getDiscoveryResultsEmptyKind({
      status: 'empty',
      candidateCount: 0,
      candidates: [],
    })).toBe('no_hits');
  });
});
