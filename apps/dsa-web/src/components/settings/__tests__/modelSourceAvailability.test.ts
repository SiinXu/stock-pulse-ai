// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  canEnableModelSource,
  collectFailedTestConnectionNames,
  isModelSourceAssignable,
  resolveModelSourceAvailability,
} from '../modelSourceAvailability';

describe('modelSourceAvailability', () => {
  it('never marks a failed test as available', () => {
    expect(resolveModelSourceAvailability({
      enabled: true,
      hasModels: true,
      issueCount: 0,
      testState: { status: 'error', text: 'auth failed' },
    })).toBe('unavailable');
    expect(isModelSourceAssignable('unavailable')).toBe(false);
    expect(canEnableModelSource({ testState: { status: 'error' } })).toBe(false);
  });

  it('requires a successful test when the wizard enforces the lifecycle gate', () => {
    expect(canEnableModelSource({
      testState: { status: 'idle' },
      requireSuccessfulTest: true,
    })).toBe(false);
    expect(canEnableModelSource({
      testState: { status: 'success' },
      requireSuccessfulTest: true,
    })).toBe(true);
  });

  it('keeps untested enabled sources out of the available badge and out of assignable lists', () => {
    expect(resolveModelSourceAvailability({
      enabled: true,
      hasModels: true,
      issueCount: 0,
      testState: { status: 'idle' },
    })).toBe('untested');
    expect(isModelSourceAssignable('untested')).toBe(false);
    expect(isModelSourceAssignable('available')).toBe(true);
  });

  it('collects connection names that failed session tests', () => {
    expect(collectFailedTestConnectionNames(
      [{ id: 'a', name: 'openai' }, { id: 'b', name: 'deepseek' }],
      { a: { status: 'error' }, b: { status: 'success' } },
    )).toEqual(['openai']);
  });
});
