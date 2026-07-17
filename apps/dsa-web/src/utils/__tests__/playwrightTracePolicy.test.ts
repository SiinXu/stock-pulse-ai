import { describe, expect, it } from 'vitest';
import {
  assertCredentialBearingFinalTracePolicy,
  resolvePlaywrightRunKey,
  resolvePlaywrightTracePolicy,
} from '../playwrightTracePolicy';

describe('Playwright run directory policy', () => {
  it('rejects a parent-directory run ID before it reaches a filesystem path', () => {
    expect(() => resolvePlaywrightRunKey('..', 'default-run'))
      .toThrow('must resolve to one portable test-results child directory');
  });

  it('rejects a current-directory run ID before it reaches a filesystem path', () => {
    expect(() => resolvePlaywrightRunKey('.', 'default-run'))
      .toThrow('must resolve to one portable test-results child directory');
  });

  it('keeps a normalized run ID as one portable directory name', () => {
    expect(resolvePlaywrightRunKey(' review run/one ', 'default-run'))
      .toBe('review-run-one');
  });
});

describe('Playwright trace policy', () => {
  it('defaults non-credential runs to trace off', () => {
    expect(resolvePlaywrightTracePolicy({}, [])).toEqual({
      credentialBearingRun: false,
      requestedTraceMode: 'off',
    });
  });

  it('allows an explicit media-free trace for non-credential debugging', () => {
    expect(resolvePlaywrightTracePolicy({ DSA_WEB_E2E_TRACE: 'retain-on-failure' }, []))
      .toEqual({
        credentialBearingRun: false,
        requestedTraceMode: 'retain-on-failure',
      });
  });

  it('rejects invalid trace modes and credential-bearing flag spellings', () => {
    expect(() => resolvePlaywrightTracePolicy({ DSA_WEB_E2E_TRACE: 'on' }, []))
      .toThrow('DSA_WEB_E2E_TRACE must be off or retain-on-failure.');
    expect(() => resolvePlaywrightTracePolicy({ DSA_WEB_E2E_CREDENTIAL_BEARING: 'True' }, []))
      .toThrow('DSA_WEB_E2E_CREDENTIAL_BEARING must be true or false.');
    expect(() => resolvePlaywrightTracePolicy({ DSA_WEB_E2E_CREDENTIAL_BEARING: '' }, []))
      .toThrow('DSA_WEB_E2E_CREDENTIAL_BEARING must be true or false.');
  });

  it('rejects environment-selected traces for credential-bearing runs', () => {
    expect(() => resolvePlaywrightTracePolicy({
      DSA_WEB_E2E_CREDENTIAL_BEARING: 'true',
      DSA_WEB_E2E_TRACE: 'retain-on-failure',
    }, [])).toThrow('Credential-bearing Playwright runs must disable trace capture.');
  });

  it('rejects both supported CLI trace override forms for credential-bearing runs', () => {
    const environment = {
      DSA_WEB_E2E_CREDENTIAL_BEARING: 'true',
      DSA_WEB_E2E_TRACE: 'off',
    };
    expect(() => resolvePlaywrightTracePolicy(environment, ['--trace', 'retain-on-failure']))
      .toThrow('Credential-bearing Playwright runs cannot enable trace capture from the CLI.');
    expect(() => resolvePlaywrightTracePolicy(environment, ['--trace=on']))
      .toThrow('Credential-bearing Playwright runs cannot enable trace capture from the CLI.');
  });

  it('allows only an explicit CLI trace-off override for credential-bearing runs', () => {
    expect(resolvePlaywrightTracePolicy({
      DSA_WEB_E2E_CREDENTIAL_BEARING: 'true',
      DSA_WEB_E2E_TRACE: 'off',
    }, ['--trace=off'])).toEqual({
      credentialBearingRun: true,
      requestedTraceMode: 'off',
    });
  });

  it.each([
    ['--ui'],
    ['--ui-host', '127.0.0.1'],
    ['--ui-host=127.0.0.1'],
    ['--ui-port', '9323'],
    ['--ui-port=9323'],
  ])('rejects Playwright UI mode for credential-bearing runs: %j', (...argv) => {
    expect(() => resolvePlaywrightTracePolicy({
      DSA_WEB_E2E_CREDENTIAL_BEARING: 'true',
      DSA_WEB_E2E_TRACE: 'off',
    }, argv)).toThrow('Credential-bearing Playwright runs cannot use UI mode.');
  });

  it.each([
    ['--config', 'alternate.config.ts'],
    ['--config=alternate.config.ts'],
    ['-c', 'alternate.config.ts'],
  ])('rejects alternate Playwright config selection for credential-bearing runs: %j', (...argv) => {
    expect(() => resolvePlaywrightTracePolicy({
      DSA_WEB_E2E_CREDENTIAL_BEARING: 'true',
      DSA_WEB_E2E_TRACE: 'off',
    }, argv)).toThrow('Credential-bearing Playwright runs must use the repository config.');
  });

  it('derives credential-bearing mode from known credential environment values', () => {
    expect(resolvePlaywrightTracePolicy({
      DSA_WEB_E2E_ALPHA_API_KEY: 'test-canary-api-key-value',
      DSA_WEB_E2E_TRACE: 'off',
    }, [])).toEqual({
      credentialBearingRun: true,
      requestedTraceMode: 'off',
    });
  });

  it('fails closed when a known credential is paired with a false marker or trace opt-in', () => {
    expect(() => resolvePlaywrightTracePolicy({
      DSA_WEB_E2E_ALPHA_API_KEY: 'test-canary-api-key-value',
      DSA_WEB_E2E_CREDENTIAL_BEARING: 'false',
      DSA_WEB_E2E_TRACE: 'off',
    }, [])).toThrow('Known Playwright credential environment values require credential-bearing mode.');
    expect(() => resolvePlaywrightTracePolicy({
      DSA_PLAYWRIGHT_ARTIFACT_CANARY: 'stockpulse-playwright-canary-value',
      DSA_WEB_E2E_TRACE: 'retain-on-failure',
    }, [])).toThrow('Credential-bearing Playwright runs must disable trace capture.');
  });

  it('validates every final project after Playwright applies CLI and project overrides', () => {
    expect(() => assertCredentialBearingFinalTracePolicy(
      { DSA_WEB_E2E_CREDENTIAL_BEARING: 'true' },
      [
        { name: 'chromium', trace: 'off' },
        { name: 'webkit', trace: 'on' },
      ],
    )).toThrow('Credential-bearing Playwright project "webkit" resolved trace to a non-off value.');

    expect(() => assertCredentialBearingFinalTracePolicy(
      { DSA_WEB_E2E_CREDENTIAL_BEARING: 'true' },
      [{ name: 'chromium', trace: { mode: 'retain-on-failure' } }],
    )).toThrow('Credential-bearing Playwright project "chromium" resolved trace to a non-off value.');

    expect(() => assertCredentialBearingFinalTracePolicy(
      { DSA_WEB_E2E_CREDENTIAL_BEARING: 'true' },
      [{ name: 'chromium', trace: 'off' }],
    )).not.toThrow();
  });
});
