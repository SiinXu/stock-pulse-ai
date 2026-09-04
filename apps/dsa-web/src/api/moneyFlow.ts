// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { createApiError, getParsedApiError } from './error';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';
import type {
  MoneyFlowView,
  MoneyFlowViewParams,
} from '../types/moneyFlow';

export type {
  MoneyFlowView,
  MoneyFlowSnapshot,
  MoneyFlowSourceAttempt,
  MoneyFlowViewParams,
} from '../types/moneyFlow';

type OpenApiMoneyFlowViewResponse = components['schemas']['MoneyFlowViewResponse'];
type OpenApiMoneyFlowSnapshotResponse = components['schemas']['MoneyFlowSnapshotResponse'];

// Compile-time anchor: hand-written camelCase types stay aligned with OpenAPI
// field sets (rename detection is structural; extra optional UI fields are fine).
type _AssertMoneyFlowView = keyof OpenApiMoneyFlowViewResponse;
type _AssertMoneyFlowSnapshot = keyof OpenApiMoneyFlowSnapshotResponse;
const _moneyFlowViewAnchor: _AssertMoneyFlowView = 'schema_version';
const _moneyFlowSnapshotAnchor: _AssertMoneyFlowSnapshot = 'amount_scale';
void _moneyFlowViewAnchor;
void _moneyFlowSnapshotAnchor;

const moneyFlowSnapshotSchema = z
  .object({
    code: z.string().min(1).max(32),
    date: z.iso.date(),
    source: z.string().min(1).max(160),
    market: z.enum(['cn', 'hk', 'us', 'jp', 'kr', 'tw']),
    mainNetInflow: z.number().finite().min(-1e18).max(1e18).nullable().optional(),
    superLargeNetInflow: z.number().finite().min(-1e18).max(1e18).nullable().optional(),
    largeNetInflow: z.number().finite().min(-1e18).max(1e18).nullable().optional(),
    mediumNetInflow: z.number().finite().min(-1e18).max(1e18).nullable().optional(),
    smallNetInflow: z.number().finite().min(-1e18).max(1e18).nullable().optional(),
    mainNetInflowRatio: z.number().finite().min(-100).max(100).nullable().optional(),
    superLargeNetInflowRatio: z.number().finite().min(-100).max(100).nullable().optional(),
    largeNetInflowRatio: z.number().finite().min(-100).max(100).nullable().optional(),
    mediumNetInflowRatio: z.number().finite().min(-100).max(100).nullable().optional(),
    smallNetInflowRatio: z.number().finite().min(-100).max(100).nullable().optional(),
    mainNetInflow5d: z.number().finite().min(-1e18).max(1e18).nullable().optional(),
    mainNetInflow10d: z.number().finite().min(-1e18).max(1e18).nullable().optional(),
    close: z.number().finite().min(0).max(1e12).nullable().optional(),
    changePct: z.number().finite().min(-100).max(1000).nullable().optional(),
    unit: z.union([z.literal('unknown'), z.string().regex(/^[A-Z]{3}$/)]),
    amountScale: z.enum([
      'unknown',
      'yuan',
      'thousand_yuan',
      'ten_thousand_yuan',
      'million_yuan',
    ]),
    bucketDefinition: z.string().min(1).max(1000),
    asOf: z.iso.datetime({ offset: true }),
    requestedDays: z.number().int().min(1).max(20),
    observedDays: z.number().int().min(1).max(20),
    completeness: z.enum(['complete', 'partial']),
    attitude: z.enum(['inflow', 'outflow', 'neutral', 'unknown']),
    calibrationNote: z.string().min(1).max(500),
  })
  .strict()
  .superRefine((value, context) => {
    const amounts = [
      value.mainNetInflow,
      value.superLargeNetInflow,
      value.largeNetInflow,
      value.mediumNetInflow,
      value.smallNetInflow,
      value.mainNetInflow5d,
      value.mainNetInflow10d,
    ];
    const calibrated = value.unit !== 'unknown' && value.amountScale !== 'unknown';
    if ((value.unit === 'unknown') !== (value.amountScale === 'unknown')) {
      context.addIssue({ code: 'custom', message: 'currency and scale disagree' });
    }
    if (!calibrated && amounts.some((amount) => amount != null)) {
      context.addIssue({ code: 'custom', message: 'uncalibrated amount exposed' });
    }
    if (value.observedDays > value.requestedDays) {
      context.addIssue({ code: 'custom', message: 'observed days exceed request' });
    }
    if (
      (value.completeness === 'complete' && value.observedDays !== value.requestedDays) ||
      (value.completeness === 'partial' && value.observedDays >= value.requestedDays)
    ) {
      context.addIssue({ code: 'custom', message: 'coverage state disagrees' });
    }
  });

const moneyFlowSourceAttemptSchema = z
  .object({
    provider: z.string().min(1).max(160),
    status: z.string().min(1).max(64).regex(/^[A-Za-z0-9_.-]+$/),
    latencyMs: z.number().finite().min(0).max(1e9).nullable().optional(),
    providerDate: z.iso.date().nullable().optional(),
    errorCode: z.string().min(1).max(120).regex(/^[A-Za-z0-9_.-]+$/).nullable().optional(),
  })
  .strict();

const moneyFlowViewSchema = z
  .object({
    schemaVersion: z.literal('money_flow_view/1.0'),
    stockCode: z.string().min(1).max(32),
    enabled: z.boolean(),
    status: z.enum([
      'disabled',
      'available',
      'partial',
      'not_supported',
      'fetch_failed',
      'empty',
      'stale',
      'fallback',
    ]),
    requestedDays: z.number().int().min(1).max(20),
    fetchedAt: z.iso.datetime({ offset: true }).nullable().optional(),
    asOf: z.iso.datetime({ offset: true }).nullable().optional(),
    providerDate: z.iso.date().nullable().optional(),
    ageDays: z.number().int().min(0).nullable().optional(),
    source: z.string().min(1).max(160).nullable().optional(),
    sourceChain: z.array(moneyFlowSourceAttemptSchema).max(16).optional(),
    market: z.enum(['cn', 'hk', 'us', 'jp', 'kr', 'tw']).nullable().optional(),
    errorCode: z.string().min(1).max(120).regex(/^[A-Za-z0-9_.-]+$/).nullable().optional(),
    warnings: z.array(z.string().min(1).max(200)).max(16).optional(),
    cacheState: z.enum(['miss', 'fresh', 'stale']).nullable().optional(),
    fallbackFrom: z.string().min(1).max(160).nullable().optional(),
    snapshot: moneyFlowSnapshotSchema.nullable().optional(),
    message: z.string().min(1).max(500).nullable().optional(),
    disclaimer: z.string().min(1).max(1000),
  })
  .strict()
  .superRefine((value, context) => {
    const dataBearing = ['available', 'partial', 'stale', 'fallback'].includes(value.status);
    if (
      (!value.enabled && value.status !== 'disabled') ||
      (value.enabled && value.status === 'disabled')
    ) {
      context.addIssue({ code: 'custom', message: 'enabled flag and status disagree' });
    }
    if (Boolean(value.snapshot) !== dataBearing) {
      context.addIssue({ code: 'custom', message: 'snapshot and status disagree' });
    }
    if (value.snapshot && (!value.asOf || !value.source || !value.providerDate)) {
      context.addIssue({ code: 'custom', message: 'data-bearing view lacks provenance' });
    }
    if (
      value.snapshot &&
      (value.snapshot.code !== value.stockCode ||
        value.snapshot.market !== value.market ||
        value.snapshot.requestedDays !== value.requestedDays ||
        value.snapshot.date !== value.providerDate)
    ) {
      context.addIssue({ code: 'custom', message: 'view and snapshot identity disagree' });
    }
    if (value.status === 'fallback' && !value.fallbackFrom) {
      context.addIssue({ code: 'custom', message: 'fallback provenance is missing' });
    }
    if (value.status === 'stale' && (!value.ageDays || value.ageDays < 1)) {
      context.addIssue({ code: 'custom', message: 'stale age is missing' });
    }
    if (['available', 'partial'].includes(value.status) && value.ageDays !== 0) {
      context.addIssue({ code: 'custom', message: 'current observation age disagrees' });
    }
    if (
      ['not_supported', 'fetch_failed', 'empty'].includes(value.status) &&
      !value.errorCode
    ) {
      context.addIssue({ code: 'custom', message: 'unavailable error code is missing' });
    }
  });

export function parseMoneyFlowView(value: unknown): MoneyFlowView {
  return parseCamelCasePayload<MoneyFlowView>(
    value,
    moneyFlowViewSchema,
    'MoneyFlowView',
    'moneyFlow',
  );
}

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
    return parseMoneyFlowView(response.data);
  } catch (error) {
    throw createApiError(getParsedApiError(error), { cause: error });
  }
}
