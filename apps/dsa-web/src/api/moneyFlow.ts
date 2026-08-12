// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { createApiError, getParsedApiError } from './error';
import { toCamelCase } from './utils';

const moneyFlowSnapshotSchema = z
  .object({
    code: z.string().optional(),
    date: z.string().optional(),
    source: z.string().optional(),
    market: z.string().optional(),
    mainNetInflow: z.number().nullable().optional(),
    superLargeNetInflow: z.number().nullable().optional(),
    largeNetInflow: z.number().nullable().optional(),
    mediumNetInflow: z.number().nullable().optional(),
    smallNetInflow: z.number().nullable().optional(),
    mainNetInflowRatio: z.number().nullable().optional(),
    superLargeNetInflowRatio: z.number().nullable().optional(),
    largeNetInflowRatio: z.number().nullable().optional(),
    mediumNetInflowRatio: z.number().nullable().optional(),
    smallNetInflowRatio: z.number().nullable().optional(),
    mainNetInflow5d: z.number().nullable().optional(),
    mainNetInflow10d: z.number().nullable().optional(),
    close: z.number().nullable().optional(),
    changePct: z.number().nullable().optional(),
    unit: z.string().optional(),
    amountScale: z.string().optional(),
    bucketDefinition: z.string().optional(),
    asOf: z.string().optional(),
    requestedDays: z.number().optional(),
    observedDays: z.number().optional(),
    completeness: z.string().optional(),
    attitude: z.string().optional(),
    calibrationNote: z.string().optional(),
  })
  .passthrough();

const moneyFlowViewSchema = z
  .object({
    schemaVersion: z.string(),
    stockCode: z.string(),
    enabled: z.boolean(),
    status: z.string(),
    requestedDays: z.number(),
    fetchedAt: z.string().nullable().optional(),
    asOf: z.string().nullable().optional(),
    providerDate: z.string().nullable().optional(),
    ageDays: z.number().nullable().optional(),
    source: z.string().nullable().optional(),
    sourceChain: z.array(z.record(z.string(), z.unknown())).optional(),
    market: z.string().nullable().optional(),
    errorCode: z.string().nullable().optional(),
    warnings: z.array(z.string()).optional(),
    cacheState: z.string().nullable().optional(),
    fallbackFrom: z.string().nullable().optional(),
    snapshot: moneyFlowSnapshotSchema.nullable().optional(),
    message: z.string().nullable().optional(),
    disclaimer: z.string(),
  })
  .passthrough();

export type MoneyFlowView = z.infer<typeof moneyFlowViewSchema>;
export type MoneyFlowSnapshot = z.infer<typeof moneyFlowSnapshotSchema>;

export type MoneyFlowViewParams = {
  stockCode: string;
  days?: number;
};

export async function getStockMoneyFlow(params: MoneyFlowViewParams): Promise<MoneyFlowView> {
  try {
    const response = await apiClient.get(
      `/api/v1/stocks/${encodeURIComponent(params.stockCode)}/money-flow`,
      {
        params: {
          days: params.days ?? 5,
        },
      },
    );
    return moneyFlowViewSchema.parse(toCamelCase(response.data) as unknown);
  } catch (error) {
    throw createApiError(getParsedApiError(error), { cause: error });
  }
}
