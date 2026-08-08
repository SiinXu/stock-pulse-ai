// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { StockBarItem, TaskInfo } from './analysis';

export interface HomeWatchlistRow {
  code: string;
  latestItem?: StockBarItem;
  analyzedToday: boolean;
  isTodayStatusLoading?: boolean;
  isTodayStatusUnknown?: boolean;
  activeTask?: TaskInfo;
}

/**
 * Per-member computed-attribute mount for T25 (scores) / T26 (focus).
 * Empty by default; consumers may attach arbitrary JSON fields.
 */
export type WatchlistMemberAttrs = Record<string, unknown>;

export interface WatchlistGroupMember {
  stockCode: string;
  sortOrder: number;
  attrs: WatchlistMemberAttrs;
}

export interface WatchlistGroup {
  id: string;
  name: string;
  sortOrder: number;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
  members: WatchlistGroupMember[];
}
