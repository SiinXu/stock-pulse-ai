// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { forwardRef } from 'react';
import { Link, type To } from 'react-router-dom';
import { cn } from '../../utils/cn';

export interface WorkspaceNavItem {
  id: string;
  label: string;
  to: To;
}

export interface WorkspaceNavigationProps extends Omit<React.HTMLAttributes<HTMLElement>, 'onChange'> {
  id: string;
  ariaLabel: string;
  current: string;
  items: readonly WorkspaceNavItem[];
  onCompactNavigate: (item: WorkspaceNavItem) => void;
}

export const WorkspaceNavigation = forwardRef<
  HTMLElement,
  WorkspaceNavigationProps
>(({
  id,
  ariaLabel,
  current,
  items,
  onCompactNavigate,
  className,
  ...props
}, ref) => {
  const currentExists = items.some((item) => item.id === current);

  return (
    <nav
      {...props}
      ref={ref}
      id={id}
      aria-label={ariaLabel}
      data-pattern="workspace-navigation"
      className={cn('min-w-0', className)}
    >
      <ul className="hidden min-w-0 flex-wrap items-end gap-1 border-b border-border md:flex">
        {items.map((item) => {
          const selected = item.id === current;
          return (
            <li key={item.id} className="min-w-0">
              <Link
                to={item.to}
                aria-current={selected ? 'page' : undefined}
                data-route-focus-key={`${id}:${item.id}`}
                className={cn(
                  'control-hit-target relative inline-flex min-h-9 max-w-full items-center border-b-2 px-3 text-sm tracking-normal transition-colors motion-reduce:transition-none',
                  'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25',
                  selected
                    ? 'border-foreground font-medium text-foreground'
                    : 'border-transparent text-secondary-text hover:border-border hover:text-foreground',
                )}
              >
                <span className="min-w-0 break-words">{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      <select
        aria-label={ariaLabel}
        value={currentExists ? current : ''}
        data-route-focus-key={`${id}:compact`}
        className="control-input-target h-9 w-full rounded-lg border border-border bg-card px-3 text-sm tracking-normal text-foreground focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25 md:hidden"
        onChange={(event) => {
          const item = items.find((candidate) => candidate.id === event.currentTarget.value);
          if (item) onCompactNavigate(item);
        }}
      >
        {!currentExists ? <option value="" disabled>{ariaLabel}</option> : null}
        {items.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select>
    </nav>
  );
});

WorkspaceNavigation.displayName = 'WorkspaceNavigation';
