// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { WatchlistGroup } from '../types/watchlist';

const memberSchema = z.object({
  stockCode: z.string(),
  sortOrder: z.number(),
  attrs: z.record(z.string(), z.unknown()).default({}),
});

const groupSchema = z.object({
  id: z.string(),
  name: z.string(),
  sortOrder: z.number(),
  isDefault: z.boolean(),
  createdAt: z.string(),
  updatedAt: z.string(),
  members: z.array(memberSchema).default([]),
});

const groupsResponseSchema = z.object({
  groups: z.array(groupSchema).default([]),
  message: z.string(),
});

async function parseGroups(data: unknown): Promise<WatchlistGroup[]> {
  const parsed = parseCamelCasePayload<{ groups: WatchlistGroup[]; message: string }>(
    data,
    groupsResponseSchema,
    'WatchlistGroupsResponse',
  );
  return parsed.groups;
}

export const watchlistGroupsApi = {
  list: async (): Promise<WatchlistGroup[]> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/stocks/watchlist/groups');
    return parseGroups(response.data);
  },

  create: async (name: string): Promise<WatchlistGroup[]> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/stocks/watchlist/groups', { name });
    return parseGroups(response.data);
  },

  rename: async (groupId: string, name: string): Promise<WatchlistGroup[]> => {
    const response = await apiClient.patch<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}`,
      { name },
    );
    return parseGroups(response.data);
  },

  remove: async (groupId: string): Promise<WatchlistGroup[]> => {
    const response = await apiClient.delete<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}`,
    );
    return parseGroups(response.data);
  },

  reorderGroups: async (orderedIds: string[]): Promise<WatchlistGroup[]> => {
    const response = await apiClient.put<Record<string, unknown>>(
      '/api/v1/stocks/watchlist/groups/reorder',
      { ordered_ids: orderedIds },
    );
    return parseGroups(response.data);
  },

  addMember: async (groupId: string, stockCode: string): Promise<WatchlistGroup[]> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}/members`,
      { stock_code: stockCode },
    );
    return parseGroups(response.data);
  },

  removeMember: async (groupId: string, stockCode: string): Promise<WatchlistGroup[]> => {
    const response = await apiClient.delete<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(stockCode)}`,
    );
    return parseGroups(response.data);
  },

  reorderMembers: async (groupId: string, orderedCodes: string[]): Promise<WatchlistGroup[]> => {
    const response = await apiClient.put<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}/members/reorder`,
      { ordered_codes: orderedCodes },
    );
    return parseGroups(response.data);
  },

  moveMember: async (params: {
    stockCode: string;
    sourceGroupId: string;
    targetGroupId: string;
    targetIndex?: number;
    copyMembership?: boolean;
  }): Promise<WatchlistGroup[]> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/stocks/watchlist/groups/move-member',
      {
        stock_code: params.stockCode,
        source_group_id: params.sourceGroupId,
        target_group_id: params.targetGroupId,
        target_index: params.targetIndex,
        copy_membership: params.copyMembership ?? false,
      },
    );
    return parseGroups(response.data);
  },
};
