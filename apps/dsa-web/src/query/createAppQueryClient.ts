// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient } from '@tanstack/react-query';

/**
 * App-root QueryClient defaults for the TanStack Query pilot.
 *
 * - `retry: false` keeps transport errors on the existing UI error surfaces
 *   (store / ApiErrorAlert) instead of introducing silent automatic retries.
 * - `refetchOnWindowFocus: true` matches the previous visibility-driven refresh.
 * - Pages that do not call useQuery / useMutation are unaffected; the provider
 *   is inert for non-consumers.
 */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: true,
      },
      mutations: {
        retry: false,
      },
    },
  });
}
