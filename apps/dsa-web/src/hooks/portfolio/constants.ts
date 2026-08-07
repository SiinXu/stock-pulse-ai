// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Shared presentation constants for Portfolio route sections.

export const PIE_COLORS = [
  'hsl(var(--primary))',
  'hsl(var(--secondary-text))',
  'hsl(var(--warning))',
  'hsl(var(--destructive))',
  'hsl(var(--muted-text))',
  'hsl(var(--foreground) / 0.65)',
];

export const PORTFOLIO_SIGNAL_LOOKUP_CONCURRENCY = 6;

export const PORTFOLIO_DATE_TRIGGER_CLASS =
  'h-11 w-full rounded-sm border border-border bg-transparent px-3 text-xs text-foreground placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text disabled:cursor-not-allowed disabled:opacity-60';
