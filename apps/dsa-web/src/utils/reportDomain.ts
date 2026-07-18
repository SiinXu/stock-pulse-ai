// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
const SECTOR_TYPE_ALIASES = new Set([
  '行业',
  '行业板块',
  'industry',
  'sector',
]);

const CONCEPT_TYPE_ALIASES = new Set([
  '概念',
  '概念板块',
  '题材',
  'concept',
  'theme',
]);

export const normalizeBoardType = (value?: string): 'sector' | 'concept' | null => {
  const normalized = (value || '').trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (SECTOR_TYPE_ALIASES.has(normalized)) {
    return 'sector';
  }
  if (CONCEPT_TYPE_ALIASES.has(normalized)) {
    return 'concept';
  }
  return null;
};
