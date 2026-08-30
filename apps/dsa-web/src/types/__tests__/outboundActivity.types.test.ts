// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations } from '../api.generated';
import * as Outbound from '../outboundActivity';
import type {
  LocalOnlyModeStatus,
  OutboundActivityItem,
  OutboundActivityListQuery,
  OutboundActivityPage,
} from '../outboundActivity';

type OpenApiLocalOnly = components['schemas']['LocalOnlyModeStatus'];
type OpenApiItem = components['schemas']['OutboundActivityItem'];
type OpenApiPage = components['schemas']['OutboundActivityPage'];
type OpenApiLocalOnlyGet200 =
  operations['get_local_only_mode_status_api_v1_security_local_only_get']['responses']['200']['content']['application/json'];
type OpenApiOutboundGet200 =
  operations['list_outbound_activity_api_v1_security_outbound_activity_get']['responses']['200']['content']['application/json'];

const ITEM_REST = {
  occurredAt: '2026-08-30T12:00:00Z',
  destinationClass: 'loopback',
  scheme: 'http',
  hostType: 'ipv4',
  reason: 'local_only_mode_blocked',
  correlationId: 'corr-1',
  localOnlyMode: true,
  allowlisted: false,
};

describe('outboundActivity OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...Outbound }).toEqual({});
    expect(Object.keys(Outbound)).toEqual([]);
    expect(Object.getOwnPropertyNames(Outbound)).toEqual([]);
  });

  it('equates path 200 JSON to the generated response components', () => {
    expectTypeOf<OpenApiLocalOnlyGet200>().toEqualTypeOf<OpenApiLocalOnly>();
    expectTypeOf<OpenApiOutboundGet200>().toEqualTypeOf<OpenApiPage>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof LocalOnlyModeStatus>().not.toMatchTypeOf<
      'env_key' | 'allowed_destination_classes'
    >();
    expectTypeOf<keyof OutboundActivityItem>().not.toMatchTypeOf<
      'occurred_at' | 'destination_class' | 'correlation_id' | 'local_only_mode'
    >();
    expectTypeOf<keyof OutboundActivityPage>().not.toMatchTypeOf<
      'local_only_mode' | 'max_retained'
    >();

    type UiHasEnvKey = 'envKey' extends keyof LocalOnlyModeStatus ? true : false;
    type UiHasEnvSnake = 'env_key' extends keyof LocalOnlyModeStatus ? true : false;
    type GeneratedHasEnvSnake = 'env_key' extends keyof OpenApiLocalOnly ? true : false;
    type UiHasAllowedClasses = 'allowedDestinationClasses' extends keyof LocalOnlyModeStatus ? true : false;
    type UiHasAllowedClassesSnake = 'allowed_destination_classes' extends keyof LocalOnlyModeStatus ? true : false;
    type GeneratedHasAllowedClassesSnake = 'allowed_destination_classes' extends keyof OpenApiLocalOnly ? true : false;
    type UiHasOccurredAt = 'occurredAt' extends keyof OutboundActivityItem ? true : false;
    type UiHasOccurredSnake = 'occurred_at' extends keyof OutboundActivityItem ? true : false;
    type GeneratedHasOccurredSnake = 'occurred_at' extends keyof OpenApiItem ? true : false;
    type UiHasDestinationClass = 'destinationClass' extends keyof OutboundActivityItem ? true : false;
    type UiHasDestinationSnake = 'destination_class' extends keyof OutboundActivityItem ? true : false;
    type GeneratedHasDestinationSnake = 'destination_class' extends keyof OpenApiItem ? true : false;
    type UiHasCorrelationId = 'correlationId' extends keyof OutboundActivityItem ? true : false;
    type UiHasCorrelationSnake = 'correlation_id' extends keyof OutboundActivityItem ? true : false;
    type GeneratedHasCorrelationSnake = 'correlation_id' extends keyof OpenApiItem ? true : false;
    type UiHasItemLocalOnly = 'localOnlyMode' extends keyof OutboundActivityItem ? true : false;
    type UiHasItemLocalOnlySnake = 'local_only_mode' extends keyof OutboundActivityItem ? true : false;
    type GeneratedHasItemLocalOnlySnake = 'local_only_mode' extends keyof OpenApiItem ? true : false;
    type UiHasPageLocalOnly = 'localOnlyMode' extends keyof OutboundActivityPage ? true : false;
    type UiHasPageLocalOnlySnake = 'local_only_mode' extends keyof OutboundActivityPage ? true : false;
    type GeneratedHasPageLocalOnlySnake = 'local_only_mode' extends keyof OpenApiPage ? true : false;
    type UiHasMaxRetained = 'maxRetained' extends keyof OutboundActivityPage ? true : false;
    type UiHasMaxRetainedSnake = 'max_retained' extends keyof OutboundActivityPage ? true : false;
    type GeneratedHasMaxRetainedSnake = 'max_retained' extends keyof OpenApiPage ? true : false;

    expectTypeOf<UiHasEnvKey>().toEqualTypeOf<true>();
    expectTypeOf<UiHasEnvSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasEnvSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasAllowedClasses>().toEqualTypeOf<true>();
    expectTypeOf<UiHasAllowedClassesSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasAllowedClassesSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasOccurredAt>().toEqualTypeOf<true>();
    expectTypeOf<UiHasOccurredSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasOccurredSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasDestinationClass>().toEqualTypeOf<true>();
    expectTypeOf<UiHasDestinationSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasDestinationSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasCorrelationId>().toEqualTypeOf<true>();
    expectTypeOf<UiHasCorrelationSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasCorrelationSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasItemLocalOnly>().toEqualTypeOf<true>();
    expectTypeOf<UiHasItemLocalOnlySnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasItemLocalOnlySnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPageLocalOnly>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPageLocalOnlySnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasPageLocalOnlySnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasMaxRetained>().toEqualTypeOf<true>();
    expectTypeOf<UiHasMaxRetainedSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasMaxRetainedSnake>().toEqualTypeOf<true>();
  });

  it('keeps UI-required arrays required while generated counterparts stay optional', () => {
    expectTypeOf<Omit<LocalOnlyModeStatus, 'allowedDestinationClasses'>>().not.toMatchTypeOf<LocalOnlyModeStatus>();
    expectTypeOf<Omit<OpenApiLocalOnly, 'allowed_destination_classes'>>().toMatchTypeOf<OpenApiLocalOnly>();
    expectTypeOf<Omit<OutboundActivityPage, 'items'>>().not.toMatchTypeOf<OutboundActivityPage>();
    expectTypeOf<Omit<OpenApiPage, 'items'>>().toMatchTypeOf<OpenApiPage>();
  });

  it('rejects decision values outside the allowed/blocked union', () => {
    expectTypeOf({ decision: 'allowed' as const, ...ITEM_REST }).toMatchTypeOf<OutboundActivityItem>();
    expectTypeOf({ decision: 'blocked' as const, ...ITEM_REST }).toMatchTypeOf<OutboundActivityItem>();
    expectTypeOf({ decision: 'maybe' as const, ...ITEM_REST }).not.toMatchTypeOf<OutboundActivityItem>();
    expectTypeOf({ decision: 'allowed' as string, ...ITEM_REST }).not.toMatchTypeOf<OutboundActivityItem>();
  });

  it('still accepts the narrow existing item, page, and status fixtures', () => {
    const item = {
      occurredAt: '2026-08-30T12:00:00Z',
      decision: 'allowed' as const,
      destinationClass: 'loopback',
      scheme: 'http',
      hostType: 'ipv4',
      reason: 'allowlisted',
      correlationId: 'corr-1',
      localOnlyMode: false,
      allowlisted: true,
    };
    const page = {
      localOnlyMode: false,
      items: [item],
      limit: 50,
      returned: 1,
      maxRetained: 200,
    };
    const status = {
      enabled: false,
      envKey: 'LOCAL_ONLY_MODE',
      policy: 'non_loopback_denied',
      allowedDestinationClasses: ['loopback'],
      blockedErrorReason: 'local_only_mode_blocked',
    };
    expectTypeOf(item).toMatchTypeOf<OutboundActivityItem>();
    expectTypeOf(page).toMatchTypeOf<OutboundActivityPage>();
    expectTypeOf(status).toMatchTypeOf<LocalOnlyModeStatus>();
  });

  it('keeps the list query handwritten optional', () => {
    expectTypeOf({}).toMatchTypeOf<OutboundActivityListQuery>();
    expectTypeOf({ limit: 20 }).toMatchTypeOf<OutboundActivityListQuery>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeStatus = {
      enabled: false,
      env_key: 'LOCAL_ONLY_MODE',
      policy: 'non_loopback_denied',
      allowed_destination_classes: ['loopback'],
      blocked_error_reason: 'local_only_mode_blocked',
    };
    expectTypeOf(snakeStatus).toMatchTypeOf<OpenApiLocalOnly>();
    expectTypeOf(snakeStatus).not.toMatchTypeOf<LocalOnlyModeStatus>();
  });
});
