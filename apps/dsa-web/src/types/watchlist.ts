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

/** Read-only, versioned projection owned by T25/T26 services. */
export interface WatchlistMemberAttrs {
  schemaVersion: 1;
  aiScore?: number | null;
  focus?: boolean | null;
}

export interface WatchlistGroupMember {
  stockCode: string;
  sortOrder: number;
  attrs: WatchlistMemberAttrs;
}

export interface WatchlistGroup {
  id: string;
  name: string;
  nameKey?: string | null;
  sortOrder: number;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
  members: WatchlistGroupMember[];
}

export interface WatchlistGroupState {
  revision: number;
  groups: WatchlistGroup[];
}
