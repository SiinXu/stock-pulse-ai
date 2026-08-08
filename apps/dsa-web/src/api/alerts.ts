import { z } from 'zod';
import { assertCamelCasePayload, parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';
import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  AlertDeleteResponse,
  AlertNotificationListQuery,
  AlertNotificationListResponse,
  AlertRuleCreateRequest,
  AlertRuleItem,
  AlertRuleListQuery,
  AlertRuleListResponse,
  AlertRuleTestResponse,
  AlertTriggerListQuery,
  AlertTriggerListResponse,
} from '../types/alerts';

type OpenApiAlertRuleItem = components['schemas']['AlertRuleItem'];
type OpenApiAlertRuleListResponse = components['schemas']['AlertRuleListResponse'];
type OpenApiAlertDeleteResponse = components['schemas']['AlertDeleteResponse'];
type OpenApiAlertRuleTestResponse = components['schemas']['AlertRuleTestResponse'];
type OpenApiAlertTriggerListResponse = components['schemas']['AlertTriggerListResponse'];
type OpenApiAlertNotificationListResponse = components['schemas']['AlertNotificationListResponse'];
type _AssertRuleItem = keyof OpenApiAlertRuleItem;
type _AssertRuleList = keyof OpenApiAlertRuleListResponse;
type _AssertDelete = keyof OpenApiAlertDeleteResponse;
type _AssertTest = keyof OpenApiAlertRuleTestResponse;
type _AssertTriggerList = keyof OpenApiAlertTriggerListResponse;
type _AssertNotificationList = keyof OpenApiAlertNotificationListResponse;
const _ruleItemAnchor: _AssertRuleItem = 'alert_type';
const _ruleListAnchor: _AssertRuleList = 'page_size';
const _deleteAnchor: _AssertDelete = 'deleted';
const _testAnchor: _AssertTest = 'rule_id';
const _triggerListAnchor: _AssertTriggerList = 'page_size';
const _notificationListAnchor: _AssertNotificationList = 'page_size';
void _ruleItemAnchor;
void _ruleListAnchor;
void _deleteAnchor;
void _testAnchor;
void _triggerListAnchor;
void _notificationListAnchor;

const alertRuleItemSchema = z.object({
  alertType: z.string(),
  cooldownActive: z.boolean().nullable().optional(),
  cooldownPolicy: z.record(z.string(), z.unknown()).nullable().optional(),
  cooldownUntil: z.string().nullable().optional(),
  createdAt: z.string().nullable().optional(),
  enabled: z.boolean(),
  id: z.number(),
  lastTriggeredAt: z.string().nullable().optional(),
  name: z.string(),
  notificationPolicy: z.record(z.string(), z.unknown()).nullable().optional(),
  parameters: z.record(z.string(), z.unknown()).optional(),
  severity: z.string(),
  source: z.string(),
  target: z.string(),
  targetScope: z.string(),
  updatedAt: z.string().nullable().optional(),
}).passthrough();

const alertRuleListResponseSchema = z.object({
  items: z.array(z.record(z.string(), z.unknown())).optional(),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
}).passthrough();

const alertDeleteResponseSchema = z.object({
  deleted: z.number(),
}).passthrough();

const alertRuleTestResponseSchema = z.object({
  degradedCount: z.number().optional(),
  evaluatedCount: z.number().optional(),
  message: z.string(),
  observedValue: z.unknown().nullable().optional(),
  ruleId: z.number(),
  skippedCount: z.number().optional(),
  status: z.string(),
  targetResults: z.array(z.record(z.string(), z.unknown())).optional(),
  targetScope: z.string().nullable().optional(),
  triggered: z.boolean(),
  triggeredCount: z.number().optional(),
}).passthrough();

const alertTriggerListResponseSchema = z.object({
  items: z.array(z.record(z.string(), z.unknown())).optional(),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
}).passthrough();

const alertNotificationListResponseSchema = z.object({
  items: z.array(z.record(z.string(), z.unknown())).optional(),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
}).passthrough();

function toAlertRuleItem(data: Record<string, unknown>): AlertRuleItem {
  const item = toCamelCase<AlertRuleItem>(data);
  if ('cooldown_policy' in data) {
    item.cooldownPolicy = data.cooldown_policy as AlertRuleItem['cooldownPolicy'];
  }
  if ('notification_policy' in data) {
    item.notificationPolicy = data.notification_policy as AlertRuleItem['notificationPolicy'];
  }
  return assertCamelCasePayload<AlertRuleItem>(item, alertRuleItemSchema, 'AlertRuleItem', 'alerts');
}

function toAlertRuleListResponse(data: Record<string, unknown>): AlertRuleListResponse {
  const response = toCamelCase<AlertRuleListResponse>(data);
  if (Array.isArray(data.items)) {
    response.items = data.items.map((item) => toAlertRuleItem(item as Record<string, unknown>));
  } else if (data.items === undefined) {
    // OpenAPI marks items optional; consumers always expect an array.
    response.items = [];
  } else {
    response.items = data.items as AlertRuleItem[];
  }
  return assertCamelCasePayload<AlertRuleListResponse>(
    response,
    alertRuleListResponseSchema,
    'AlertRuleListResponse',
    'alerts',
  );
}

function omitUndefined(input: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(input).filter(([, value]) => value !== undefined),
  );
}

function toSnakeRulePayload(payload: AlertRuleCreateRequest): Record<string, unknown> {
  const request: Record<string, unknown> = {};
  if (payload.name !== undefined) request.name = payload.name;
  if (payload.targetScope !== undefined) request.target_scope = payload.targetScope;
  if (payload.target !== undefined) request.target = payload.target;
  if (payload.alertType !== undefined) request.alert_type = payload.alertType;
  if (payload.severity !== undefined) request.severity = payload.severity;
  if (payload.enabled !== undefined) request.enabled = payload.enabled;
  if (payload.cooldownPolicy !== undefined) request.cooldown_policy = payload.cooldownPolicy;
  if (payload.parameters !== undefined) {
    request.parameters = omitUndefined({
      direction: payload.parameters.direction,
      price: payload.parameters.price,
      change_pct: payload.parameters.changePct,
      multiplier: payload.parameters.multiplier,
      window: payload.parameters.window,
      period: payload.parameters.period,
      threshold: payload.parameters.threshold,
      fast_period: payload.parameters.fastPeriod,
      slow_period: payload.parameters.slowPeriod,
      signal_period: payload.parameters.signalPeriod,
      k_period: payload.parameters.kPeriod,
      d_period: payload.parameters.dPeriod,
      mode: payload.parameters.mode,
      statuses: payload.parameters.statuses,
      min_drop: payload.parameters.minDrop,
      event_categories: payload.parameters.eventCategories,
      lookback_hours: payload.parameters.lookbackHours,
      min_items: payload.parameters.minItems,
    });
  }
  return request;
}

function toRuleListParams(query: AlertRuleListQuery = {}): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {};
  if (query.enabled !== undefined) params.enabled = query.enabled;
  if (query.alertType) params.alert_type = query.alertType;
  if (query.targetScope) params.target_scope = query.targetScope;
  if (query.target) params.target = query.target;
  if (query.source) params.source = query.source;
  if (query.page !== undefined) params.page = query.page;
  if (query.pageSize !== undefined) params.page_size = query.pageSize;
  return params;
}

function toTriggerListParams(query: AlertTriggerListQuery = {}): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.ruleId !== undefined) params.rule_id = query.ruleId;
  if (query.target) params.target = query.target;
  if (query.status) params.status = query.status;
  if (query.page !== undefined) params.page = query.page;
  if (query.pageSize !== undefined) params.page_size = query.pageSize;
  return params;
}

function toNotificationListParams(query: AlertNotificationListQuery = {}): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {};
  if (query.triggerId !== undefined) params.trigger_id = query.triggerId;
  if (query.channel) params.channel = query.channel;
  if (query.success !== undefined) params.success = query.success;
  if (query.page !== undefined) params.page = query.page;
  if (query.pageSize !== undefined) params.page_size = query.pageSize;
  return params;
}

export const alertsApi = {
  async listRules(query: AlertRuleListQuery = {}): Promise<AlertRuleListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/alerts/rules', {
      params: toRuleListParams(query),
    });
    return toAlertRuleListResponse(response.data);
  },

  async createRule(payload: AlertRuleCreateRequest): Promise<AlertRuleItem> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/alerts/rules',
      toSnakeRulePayload(payload),
    );
    return toAlertRuleItem(response.data);
  },

  async getRule(ruleId: number): Promise<AlertRuleItem> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/alerts/rules/${ruleId}`);
    return toAlertRuleItem(response.data);
  },

  async updateRule(ruleId: number, payload: AlertRuleCreateRequest): Promise<AlertRuleItem> {
    const response = await apiClient.patch<Record<string, unknown>>(
      `/api/v1/alerts/rules/${ruleId}`,
      toSnakeRulePayload(payload),
    );
    return toAlertRuleItem(response.data);
  },

  async deleteRule(ruleId: number): Promise<AlertDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/alerts/rules/${ruleId}`);
    return parseCamelCasePayload<AlertDeleteResponse>(
      response.data,
      alertDeleteResponseSchema,
      'AlertDeleteResponse',
      'alerts',
    );
  },

  async enableRule(ruleId: number): Promise<AlertRuleItem> {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/alerts/rules/${ruleId}/enable`);
    return toAlertRuleItem(response.data);
  },

  async disableRule(ruleId: number): Promise<AlertRuleItem> {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/alerts/rules/${ruleId}/disable`);
    return toAlertRuleItem(response.data);
  },

  async testRule(ruleId: number): Promise<AlertRuleTestResponse> {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/alerts/rules/${ruleId}/test`);
    return parseCamelCasePayload<AlertRuleTestResponse>(
      response.data,
      alertRuleTestResponseSchema,
      'AlertRuleTestResponse',
      'alerts',
    );
  },

  async listTriggers(query: AlertTriggerListQuery = {}): Promise<AlertTriggerListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/alerts/triggers', {
      params: toTriggerListParams(query),
    });
    const list = parseCamelCasePayload<AlertTriggerListResponse>(
      response.data,
      alertTriggerListResponseSchema,
      'AlertTriggerListResponse',
      'alerts',
    );
    if (!Array.isArray(list.items)) {
      return { ...list, items: [] };
    }
    return list;
  },

  async listNotifications(query: AlertNotificationListQuery = {}): Promise<AlertNotificationListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/alerts/notifications', {
      params: toNotificationListParams(query),
    });
    const list = parseCamelCasePayload<AlertNotificationListResponse>(
      response.data,
      alertNotificationListResponseSchema,
      'AlertNotificationListResponse',
      'alerts',
    );
    if (!Array.isArray(list.items)) {
      return { ...list, items: [] };
    }
    return list;
  },
};
