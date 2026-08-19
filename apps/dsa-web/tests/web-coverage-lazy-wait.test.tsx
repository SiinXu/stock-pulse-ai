import { useEffect, useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS,
  WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS,
} from '../src/test-utils/coverageTimeouts';

function DelayedDiagnostics({ delayMs }: { delayMs: number }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setReady(true), delayMs);
    return () => window.clearTimeout(id);
  }, [delayMs]);
  if (!ready) {
    return null;
  }
  return <div data-testid="run-diagnostics" />;
}

describe('coverage lazy diagnostics wait', () => {
  it('finds run-diagnostics after it appears later than the default RTL wait', async () => {
    const delayMs = WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS + 400;
    render(<DelayedDiagnostics delayMs={delayMs} />);
    expect(screen.queryByTestId('run-diagnostics')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('run-diagnostics')).toBeInTheDocument();
    }, { timeout: WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS });
  });
});
