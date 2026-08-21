// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { SOURCE_CANDIDATE_DISCOVERY_TEXT } from '../../../locales/candidateDiscoveryText';
import { SCREENING_TEXT } from '../../../locales/screening';
import type { DiscoveryScreeningText } from '../screeningText';
import {
  createDiscoveryResultsEmptyState,
  getDiscoveryResultsEmptyKind,
} from '../discoveryEmptyState';

const text = {
  ...SCREENING_TEXT.en,
  ...SOURCE_CANDIDATE_DISCOVERY_TEXT.en,
} as DiscoveryScreeningText;

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

describe('createDiscoveryResultsEmptyState', () => {
  it('does not diagnose an empty universe as a data-source outage', () => {
    const state = createDiscoveryResultsEmptyState({
      text,
      kind: 'unconfigured',
      loading: false,
      onOpenDataSources: () => undefined,
      onRetry: () => undefined,
    });
    expect(state.title).toBe(text.diagnosticEmpty);
    expect(state.description).toBe(text.noHitsDescription);
    expect(state.title).not.toBe(text.sourcesUnavailableTitle);
    expect(state.description).not.toBe(text.sourcesUnavailableDescription);
    expect(state.title).not.toBe(text.discoveryNoHits);
  });
});
