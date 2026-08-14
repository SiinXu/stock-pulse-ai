// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Typed client for GET /api/v1/portfolio/health (operation_id getPortfolioHealth).

import { z } from 'zod';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { PortfolioHealthSummary } from '../types/portfolioHealth';

const portfolioHealthBandSchema = z.enum(['healthy', 'fair', 'caution', 'poor']);
const portfolioHealthStatusSchema = z.enum([
  'ok',
  'partial',
  'empty_portfolio',
  'unavailable',
]);

const portfolioHealthResponseSchema = z
  .object({
    accountId: z.number().int().nullable().optional(),
    asOf: z.string().min(1),
    band: portfolioHealthBandSchema.nullable().optional(),
    comparable: z.boolean(),
    costMethod: z.enum(['fifo', 'avg']),
    coverageRatio: z.number(),
    currency: z.string().min(1),
    score: z.number().nullable().optional(),
    partialScore: z.number().nullable().optional(),
    status: portfolioHealthStatusSchema,
    statusMessage: z.string().nullable().optional(),
    disclaimer: z.string().optional(),
  })
  .passthrough();

export const portfolioHealthApi = {
  /**
   * Read-only stored daily snapshot. Never computes or persists.
   * 404 means no snapshot yet (empty / not refreshed).
   */
  async getSummary(): Promise<PortfolioHealthSummary | null> {
    try {
      const response = await apiClient.get<unknown>(
        '/api/v1/portfolio/health',
        locallyRecoverableResourceConfig(),
      );
      return parseCamelCasePayload<PortfolioHealthSummary>(
        response.data,
        portfolioHealthResponseSchema,
        'portfolio health',
      );
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404) return null;
      throw error;
    }
  },
};
