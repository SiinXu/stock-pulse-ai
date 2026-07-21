// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { keyBelongsToSection, placementForKey } from '../settingsFieldPlacement';

describe('placementForKey', () => {
  it('splits notification report-output fields into the Reports section', () => {
    for (const key of [
      'REPORT_TYPE',
      'REPORT_LANGUAGE',
      'REPORT_SUMMARY_ONLY',
      'REPORT_SHOW_LLM_MODEL',
      'REPORT_INTEGRITY_ENABLED',
      'REPORT_HISTORY_COMPARE_N',
    ]) {
      expect(placementForKey('notification', key)).toEqual({ section: 'reports', view: 'output' });
    }
  });

  it('splits notification delivery rules into the Alerts routing / behavior views', () => {
    for (const key of [
      'NOTIFICATION_REPORT_CHANNELS',
      'NOTIFICATION_ALERT_CHANNELS',
      'MERGE_EMAIL_NOTIFICATION',
    ]) {
      expect(placementForKey('notification', key)).toEqual({ section: 'alerts', view: 'routing' });
    }
    for (const key of [
      'NOTIFICATION_DEDUP_TTL_SECONDS',
      'NOTIFICATION_QUIET_HOURS',
      'NOTIFICATION_MIN_SEVERITY',
      'SINGLE_STOCK_NOTIFY',
    ]) {
      expect(placementForKey('notification', key)).toEqual({ section: 'alerts', view: 'behavior' });
    }
  });

  it('keeps concrete notification channels in the Notifications section', () => {
    for (const key of ['WECHAT_WEBHOOK_URL', 'FEISHU_APP_ID', 'TELEGRAM_BOT_TOKEN', 'CUSTOM_WEBHOOK_URLS']) {
      expect(placementForKey('notification', key)).toEqual({ section: 'notifications', view: 'channels' });
    }
  });

  it('routes agent Event Monitor to Alerts and context compression to Conversation', () => {
    for (const key of ['AGENT_EVENT_MONITOR_ENABLED', 'AGENT_EVENT_MONITOR_INTERVAL_MINUTES', 'AGENT_EVENT_ALERT_RULES_JSON']) {
      expect(placementForKey('agent', key)).toEqual({ section: 'alerts', view: 'events' });
    }
    for (const key of ['AGENT_CONTEXT_COMPRESSION_ENABLED', 'AGENT_CONTEXT_PROTECTED_TURNS']) {
      expect(placementForKey('agent', key)).toEqual({ section: 'conversation', view: 'context' });
    }
  });

  it('keeps ordinary agent behavior fields under Agent Behavior', () => {
    for (const key of ['AGENT_MODE', 'AGENT_MAX_STEPS', 'AGENT_MEMORY_ENABLED', 'AGENT_ORCHESTRATOR_MODE']) {
      expect(placementForKey('agent', key)).toEqual({ section: 'agent_behavior', view: 'execution' });
    }
  });

  it('routes internal HMAC and low-level tuning keys to the Advanced diagnostics view', () => {
    for (const key of [
      'LLM_USAGE_HMAC_SECRET',
      'LLM_USAGE_HMAC_KEY_VERSION',
      'GENERATION_BACKEND_MAX_CONCURRENCY',
      'GENERATION_BACKEND_TIMEOUT_SECONDS',
      'LOCAL_CLI_BACKEND_MAX_CONCURRENCY',
    ]) {
      expect(placementForKey('ai_model', key)).toEqual({ section: 'advanced', view: 'diagnostics' });
    }
    // A non-internal ai_model key stays with AI & Models; the backend *choice*
    // (not the tuning limits) stays with the AI section too.
    expect(placementForKey('ai_model', 'LITELLM_MODEL').section).toBe('ai_models');
    expect(placementForKey('ai_model', 'GENERATION_BACKEND').section).toBe('ai_models');
  });

  it('splits system keys across the System & Security views', () => {
    // Scheduler keys render via the dedicated card on the Scheduling tab.
    for (const key of ['SCHEDULE_ENABLED', 'SCHEDULE_TIME', 'SCHEDULE_TIMES', 'SCHEDULE_RUN_IMMEDIATELY']) {
      expect(placementForKey('system', key)).toEqual({ section: 'system_security', view: 'runtime' });
    }
    // ADMIN_AUTH_ENABLED renders via the auth card on the Auth & Security tab.
    expect(placementForKey('system', 'ADMIN_AUTH_ENABLED')).toEqual({ section: 'system_security', view: 'security' });
    // Web service / logging knobs live on Web & Logs.
    for (const key of ['LOG_LEVEL', 'WEBUI_PORT', 'DEBUG']) {
      expect(placementForKey('system', key)).toEqual({ section: 'system_security', view: 'service' });
    }
    // Remaining system fields (and unknown keys) land on the General tab.
    for (const key of ['MAX_WORKERS', 'MARKET_REVIEW_ENABLED', 'SOME_FUTURE_SYSTEM_KEY']) {
      expect(placementForKey('system', key)).toEqual({ section: 'system_security', view: 'general' });
    }
  });

  it('delegates other categories to the coarse category mapping', () => {
    expect(placementForKey('backtest', 'BACKTEST_ENABLED')).toEqual({ section: 'backtesting', view: 'engine' });
    expect(placementForKey('base', 'STOCK_LIST')).toEqual({ section: 'overview', view: 'readiness' });
  });

  it('keyBelongsToSection reflects the resolved placement', () => {
    expect(keyBelongsToSection('notification', 'REPORT_TYPE', 'reports')).toBe(true);
    expect(keyBelongsToSection('notification', 'REPORT_TYPE', 'alerts')).toBe(false);
    expect(keyBelongsToSection('agent', 'AGENT_CONTEXT_PROTECTED_TURNS', 'conversation')).toBe(true);
    expect(keyBelongsToSection('agent', 'AGENT_MODE', 'conversation')).toBe(false);
  });
});
