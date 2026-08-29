// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// @vitest-environment node
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { createAppQueryClient } from '../src/query/createAppQueryClient';

const webRoot = process.cwd();

function read(relativePath: string): string {
  return readFileSync(path.join(webRoot, relativePath), 'utf8');
}

describe('Query consumer hosts', () => {
  it('keeps production QueryClient defaults retry-free with focus refetch on', () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.retry).toBe(false);
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    expect(client.getDefaultOptions().mutations?.retry).toBe(false);
  });

  it('wraps every real useUnreadNotifications host with the production retry-free client', () => {
    expect(read('src/main.tsx')).toContain('<QueryProvider>');
    expect(read('e2e/application-shell-fixture.tsx')).toContain('<QueryProvider>');
    expect(read('src/App.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/layout/__tests__/RouteBoundary.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/playground/__tests__/scenarios.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useUnreadNotifications.test.tsx')).toContain('createAppQueryClient');
  });

  it('wraps NotificationCenterPage tests with the production retry-free client', () => {
    expect(read('src/pages/__tests__/NotificationCenterPage.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/pages/__tests__/NotificationCenterPage.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useNotificationCenterInbox.test.tsx')).toContain('createAppQueryClient');
  });
});
