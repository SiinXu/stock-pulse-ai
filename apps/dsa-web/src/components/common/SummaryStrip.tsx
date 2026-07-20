// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export type SummaryStripTone = 'default' | 'success' | 'warning' | 'danger';

export interface SummaryStripItem {
  id: string;
  label: React.ReactNode;
  value: React.ReactNode;
  detail?: React.ReactNode;
  tone?: SummaryStripTone;
}

export interface SummaryStripProps extends React.HTMLAttributes<HTMLDListElement> {
  items: readonly SummaryStripItem[];
  'aria-label': string;
}

const VALUE_TONE_STYLES: Record<SummaryStripTone, string> = {
  default: 'text-foreground',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
};

export const SummaryStrip = forwardRef<
  HTMLDListElement,
  SummaryStripProps
>(({
  items,
  className,
  ...props
}, ref) => (
  <dl
    {...props}
    ref={ref}
    data-pattern="summary-strip"
    className={cn(
      'grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,12rem),1fr))] gap-x-6 gap-y-4 border-y border-border py-4',
      className,
    )}
  >
    {items.map((item) => (
      <div key={item.id} data-summary-id={item.id} className="min-w-0 border-l-2 border-border pl-3">
        <dt className="break-words text-xs font-medium tracking-normal text-secondary-text">{item.label}</dt>
        <dd className={cn('mt-1 min-w-0 break-words text-xl font-semibold tracking-normal', VALUE_TONE_STYLES[item.tone ?? 'default'])}>
          {item.value}
        </dd>
        {item.detail ? <dd className="mt-1 break-words text-xs text-muted-text">{item.detail}</dd> : null}
      </div>
    ))}
  </dl>
));

SummaryStrip.displayName = 'SummaryStrip';
