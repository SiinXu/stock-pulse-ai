// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { LocalModelRuntimeState } from '../../../types/localModels';
import type { GenerationBackendStatusResponse } from '../../../types/systemConfig';
import {
  formatHubCheckedAt,
  localRuntimeStatusLabelKey,
  summarizeLocalCliStatus,
  summarizeLocalRuntimeStatus,
} from '../modelSourcesHubStatus';

function runtime(status: LocalModelRuntimeState['status']): LocalModelRuntimeState {
  return {
    runtime: 'ollama',
    status,
    installedModels: [],
    manualPullSupported: true,
    localInstallPlatform: null,
    configuration: {
      configVersion: '1',
      registeredModels: [],
      primaryModel: '',
      agentModel: '',
    },
  };
}

function cliStatus(
  overrides: Partial<GenerationBackendStatusResponse['primary']> & {
    backendType: 'litellm' | 'local_cli';
    backendId: string;
  },
): GenerationBackendStatusResponse {
  return {
    primaryBackendId: overrides.backendId,
    fallbackBackendId: null,
    primary: {
      providerId: overrides.backendId,
      available: false,
      healthStatus: 'not_tested',
      supportsJson: false,
      supportsStream: false,
      supportsTools: false,
      supportsVision: false,
      isPrimary: true,
      maxConcurrency: 1,
      usageAvailable: false,
      ...overrides,
    },
    fallback: null,
    backends: [],
  };
}

describe('modelSourcesHubStatus', () => {
  it('never treats local runtime probe errors as available', () => {
    const summary = summarizeLocalRuntimeStatus('error', null, 'connection refused');
    expect(summary.availability).toBe('failed');
    expect(summary.tone).toBe('danger');
    expect(summary.failureReason).toBe('connection refused');
  });

  it('maps local runtime statuses honestly', () => {
    expect(summarizeLocalRuntimeStatus('idle', runtime('running')).availability).toBe('available');
    expect(summarizeLocalRuntimeStatus('idle', runtime('not-installed')).availability).toBe('not_configured');
    expect(summarizeLocalRuntimeStatus('idle', runtime('unavailable')).availability).toBe('unavailable');
    expect(summarizeLocalRuntimeStatus('idle', runtime('unknown')).availability).toBe('unavailable');
    expect(summarizeLocalRuntimeStatus('loading', null).availability).toBe('loading');
  });

  it('reuses local-models status label keys', () => {
    expect(localRuntimeStatusLabelKey('running')).toBe('runtimeRunning');
    expect(localRuntimeStatusLabelKey('not-installed')).toBe('runtimeMissing');
  });

  it('treats non-CLI backends as not configured', () => {
    const summary = summarizeLocalCliStatus(
      'idle',
      cliStatus({ backendId: 'litellm', backendType: 'litellm', available: true, healthStatus: 'passed' }),
    );
    expect(summary.availability).toBe('not_configured');
  });

  it('surfaces CLI detection failures with reasons', () => {
    const summary = summarizeLocalCliStatus(
      'idle',
      cliStatus({
        backendId: 'codex_cli',
        backendType: 'local_cli',
        available: false,
        healthStatus: 'failed',
        lastErrorCode: 'cli_not_found',
        lastErrorMessage: 'missing binary',
      }),
    );
    expect(summary.availability).toBe('unavailable');
    expect(summary.failureReason).toContain('cli_not_found');
    expect(summary.failureReason).toContain('missing binary');
  });

  it('formats checked-at timestamps', () => {
    expect(formatHubCheckedAt(null, 'en-US')).toBeNull();
    expect(formatHubCheckedAt(1_700_000_000_000, 'en-US')).toEqual(expect.any(String));
  });
});
