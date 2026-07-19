// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  type AiModelSaveGate,
  classifyAiModelGate,
  computeGroupFingerprint,
} from '../autosaveMachine';

const clearGate: AiModelSaveGate = {
  catalogLoading: false,
  catalogError: false,
  schemaUnavailable: false,
  channelDraftValid: true,
  changesConnection: false,
  connectionRespectsSchema: true,
};

describe('computeGroupFingerprint', () => {
  it('is stable for identical item lists and differs when content changes', () => {
    const a = computeGroupFingerprint([{ key: 'WEBUI_PORT', value: '9000' }]);
    const b = computeGroupFingerprint([{ key: 'WEBUI_PORT', value: '9000' }]);
    const c = computeGroupFingerprint([{ key: 'WEBUI_PORT', value: '9001' }]);
    expect(a).toBe(b);
    expect(a).not.toBe(c);
  });
});

describe('classifyAiModelGate', () => {
  it('is clear to persist when nothing blocks the draft', () => {
    expect(classifyAiModelGate(clearGate, { checkConnection: true })).toBeNull();
    expect(classifyAiModelGate(clearGate, { checkConnection: false })).toBeNull();
  });

  it('schedules (does not fail) while the Provider Catalog is loading or errored', () => {
    expect(classifyAiModelGate({ ...clearGate, catalogLoading: true }, { checkConnection: true })).toBe('scheduled');
    expect(classifyAiModelGate({ ...clearGate, catalogError: true }, { checkConnection: false })).toBe('scheduled');
  });

  it('fails when the connection schema is unavailable or the channel draft is invalid', () => {
    expect(classifyAiModelGate({ ...clearGate, schemaUnavailable: true }, { checkConnection: true })).toBe('failed');
    expect(classifyAiModelGate({ ...clearGate, channelDraftValid: false }, { checkConnection: true })).toBe('failed');
  });

  it('enforces the Connection schema contract only on the run pass', () => {
    const violating: AiModelSaveGate = {
      ...clearGate,
      changesConnection: true,
      connectionRespectsSchema: false,
    };
    expect(classifyAiModelGate(violating, { checkConnection: true })).toBe('failed');
    // The scheduling pass debounces connection edits instead of failing them.
    expect(classifyAiModelGate(violating, { checkConnection: false })).toBeNull();
  });

  it('prioritises catalog readiness over schema and channel failures', () => {
    const gate: AiModelSaveGate = {
      ...clearGate,
      catalogLoading: true,
      schemaUnavailable: true,
      channelDraftValid: false,
    };
    expect(classifyAiModelGate(gate, { checkConnection: true })).toBe('scheduled');
  });
});
