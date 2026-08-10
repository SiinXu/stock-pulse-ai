// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { WatchlistGroupState } from '../types/watchlist';

const memberSchema = z.object({
  stockCode: z.string().min(1).max(32),
  sortOrder: z.number().int().nonnegative(),
  attrs: z.object({
    schemaVersion: z.literal(1),
    aiScore: z.number().finite().min(0).max(100).nullish(),
    focus: z.boolean().nullish(),
  }),
});

const groupSchema = z.object({
  id: z.string().min(1).max(64),
  name: z.string().min(1).max(80),
  nameKey: z.string().max(128).nullish(),
  sortOrder: z.number().int().nonnegative(),
  isDefault: z.boolean(),
  createdAt: z.string().datetime({ offset: true }),
  updatedAt: z.string().datetime({ offset: true }),
  members: z.array(memberSchema).max(500),
});

const groupsResponseSchema = z.object({
  revision: z.number().int().positive(),
  groups: z.array(groupSchema).max(50),
  message: z.string().max(160),
}).superRefine((value, context) => {
  const totalMemberships = value.groups.reduce((total, group) => total + group.members.length, 0);
  if (totalMemberships > 2_000) {
    context.addIssue({
      code: 'custom',
      message: 'Watchlist group response exceeds membership limit',
      path: ['groups'],
    });
  }
});

function parseState(data: unknown): WatchlistGroupState {
  const parsed = parseCamelCasePayload<WatchlistGroupState & { message: string }>(
    data,
    groupsResponseSchema,
    'WatchlistGroupsResponse',
  );
  return { revision: parsed.revision, groups: parsed.groups };
}

export const watchlistGroupsApi = {
  list: async (): Promise<WatchlistGroupState> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/stocks/watchlist/groups');
    return parseState(response.data);
  },

  create: async (name: string, expectedRevision: number): Promise<WatchlistGroupState> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/stocks/watchlist/groups', {
      name,
      expected_revision: expectedRevision,
    });
    return parseState(response.data);
  },

  rename: async (groupId: string, name: string, expectedRevision: number): Promise<WatchlistGroupState> => {
    const response = await apiClient.patch<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}`,
      { name, expected_revision: expectedRevision },
    );
    return parseState(response.data);
  },

  remove: async (groupId: string, expectedRevision: number): Promise<WatchlistGroupState> => {
    const response = await apiClient.delete<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}`,
      { params: { expected_revision: expectedRevision } },
    );
    return parseState(response.data);
  },

  reorderGroups: async (orderedIds: string[], expectedRevision: number): Promise<WatchlistGroupState> => {
    const response = await apiClient.put<Record<string, unknown>>(
      '/api/v1/stocks/watchlist/groups/reorder',
      { ordered_ids: orderedIds, expected_revision: expectedRevision },
    );
    return parseState(response.data);
  },

  addMember: async (groupId: string, stockCode: string, expectedRevision: number): Promise<WatchlistGroupState> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}/members`,
      { stock_code: stockCode, expected_revision: expectedRevision },
    );
    return parseState(response.data);
  },

  removeMember: async (groupId: string, stockCode: string, expectedRevision: number): Promise<WatchlistGroupState> => {
    const response = await apiClient.delete<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(stockCode)}`,
      { params: { expected_revision: expectedRevision } },
    );
    return parseState(response.data);
  },

  reorderMembers: async (
    groupId: string,
    orderedCodes: string[],
    expectedRevision: number,
  ): Promise<WatchlistGroupState> => {
    const response = await apiClient.put<Record<string, unknown>>(
      `/api/v1/stocks/watchlist/groups/${encodeURIComponent(groupId)}/members/reorder`,
      { ordered_codes: orderedCodes, expected_revision: expectedRevision },
    );
    return parseState(response.data);
  },

  moveMember: async (params: {
    stockCode: string;
    sourceGroupId: string;
    targetGroupId: string;
    targetIndex?: number;
    copyMembership?: boolean;
    expectedRevision: number;
  }): Promise<WatchlistGroupState> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/stocks/watchlist/groups/move-member',
      {
        stock_code: params.stockCode,
        source_group_id: params.sourceGroupId,
        target_group_id: params.targetGroupId,
        target_index: params.targetIndex,
        copy_membership: params.copyMembership ?? false,
        expected_revision: params.expectedRevision,
      },
    );
    return parseState(response.data);
  },
};
