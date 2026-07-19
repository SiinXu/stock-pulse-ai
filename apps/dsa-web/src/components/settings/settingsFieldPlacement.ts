// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Field-level placement map: which settings `section / view` owns each config
// key. This is the authoritative source for content rendering, per-section
// status badges and cross-section error jumps, and it supersedes the coarse
// `legacyToSectionView(category, sub)` fallback for the keys that need to move
// out of their backend category.
//
// Motivation (Phase 4.6D1): several first-level sections collapse to the same
// backend (category, sub) — Reports and Alerts both live under `notification`,
// Conversation and Agent Behavior both under `agent`. Without a key-level map
// they render identical content and cannot get independent badges. This module
// splits those buckets by key so each section owns a distinct field set.

import {
  legacyToSectionView,
  type SectionViewTarget,
} from './settingsInformationArchitecture';
import { getNotificationFieldGroupId } from './notificationFieldGroups';
import { isNotificationChannelKey } from './notificationChannels';
import { getSubCategoryOfKey } from './settingsSubCategories';

const REPORTS_TARGET: SectionViewTarget = { section: 'reports', view: 'output' };
const ALERTS_TARGET: SectionViewTarget = { section: 'alerts', view: 'rules' };
const NOTIFICATIONS_TARGET: SectionViewTarget = { section: 'notifications', view: 'channels' };
const CONVERSATION_TARGET: SectionViewTarget = { section: 'conversation', view: 'context' };
const AGENT_TARGET: SectionViewTarget = { section: 'agent_behavior', view: 'execution' };
const ADVANCED_TARGET: SectionViewTarget = { section: 'advanced', view: 'raw_config' };

// Internal / low-level keys that belong under the top-level Advanced section
// rather than cluttering the everyday AI & Models views (MC-18). Kept explicit
// so only vetted keys move; everything else keeps its category placement.
const ADVANCED_KEYS = new Set<string>([
  // Usage-signing secrets.
  'LLM_USAGE_HMAC_SECRET',
  'LLM_USAGE_HMAC_KEY_VERSION',
  // Low-level execution backend / CLI tuning limits (not the backend choice
  // itself — that stays under Reliability).
  'GENERATION_BACKEND_MAX_CONCURRENCY',
  'GENERATION_BACKEND_MAX_OUTPUT_BYTES',
  'GENERATION_BACKEND_TIMEOUT_SECONDS',
  'LOCAL_CLI_BACKEND_MAX_CONCURRENCY',
]);

/**
 * Resolve the owning section/view for a single config key.
 *
 * Explicit key-level rules win; anything not matched delegates to the coarse
 * category→section mapping so unknown/newly-added keys still land somewhere
 * sensible instead of disappearing.
 */
export function placementForKey(category: string, key: string): SectionViewTarget {
  const upper = key.toUpperCase();

  if (ADVANCED_KEYS.has(upper)) {
    return ADVANCED_TARGET;
  }

  if (category === 'notification') {
    if (isNotificationChannelKey(upper)) {
      return NOTIFICATIONS_TARGET;
    }
    // Non-channel notification fields split into report output vs delivery
    // rules (routing / dedup / severity / digest) via the existing grouping.
    return getNotificationFieldGroupId(upper) === 'report' ? REPORTS_TARGET : ALERTS_TARGET;
  }

  if (category === 'agent') {
    // Event Monitor is an alerting concern (rendered in the Alerts section via a
    // dedicated card); context compression is a conversation concern; everything
    // else is agent execution behavior.
    if (upper.startsWith('AGENT_EVENT_')) {
      return ALERTS_TARGET;
    }
    if (upper.startsWith('AGENT_CONTEXT_')) {
      return CONVERSATION_TARGET;
    }
    return AGENT_TARGET;
  }

  const sub = getSubCategoryOfKey(category, key);
  return legacyToSectionView(category, sub);
}

/**
 * Does a config key belong to the given section? Used to filter a backend
 * category's items down to the fields a section should render.
 */
export function keyBelongsToSection(category: string, key: string, section: string): boolean {
  return placementForKey(category, key).section === section;
}
