// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { forwardRef, useRef } from 'react';
import { cn } from '../../utils/cn';
import { getTabId, getTabPanelId } from './tabIds';

export interface TabItem {
  id: string;
  label: React.ReactNode;
  disabled?: boolean;
}

export interface TabsProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange' | 'role'> {
  id: string;
  value: string;
  items: readonly TabItem[];
  onValueChange: (value: string) => void;
  'aria-label': string;
}

export const Tabs = forwardRef<
  HTMLDivElement,
  TabsProps
>(({
  id,
  value,
  items,
  onValueChange,
  className,
  ...props
}, ref) => {
  const triggerRefs = useRef(new Map<string, HTMLButtonElement>());

  const activate = (item: TabItem) => {
    if (item.disabled) return;
    onValueChange(item.id);
    triggerRefs.current.get(item.id)?.focus();
  };

  const move = (currentIndex: number, direction: 1 | -1) => {
    for (let offset = 1; offset <= items.length; offset += 1) {
      const nextIndex = (currentIndex + direction * offset + items.length) % items.length;
      const nextItem = items[nextIndex];
      if (!nextItem.disabled) {
        activate(nextItem);
        return;
      }
    }
  };

  const moveToEdge = (fromEnd: boolean) => {
    const candidates = fromEnd ? [...items].reverse() : items;
    const nextItem = candidates.find((item) => !item.disabled);
    if (nextItem) activate(nextItem);
  };

  return (
    <div
      {...props}
      ref={ref}
      id={id}
      role="tablist"
      aria-orientation="horizontal"
      data-pattern="tabs"
      className={cn('flex max-w-full items-end gap-1 overflow-x-auto border-b border-border', className)}
    >
      {items.map((item, index) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            ref={(node) => {
              if (node) triggerRefs.current.set(item.id, node);
              else triggerRefs.current.delete(item.id);
            }}
            id={getTabId(id, item.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={getTabPanelId(id, item.id)}
            tabIndex={selected ? 0 : -1}
            disabled={item.disabled}
            data-control="tab"
            className={cn(
              'control-hit-target relative inline-flex h-9 shrink-0 items-center justify-center border-b-2 px-3 text-sm tracking-normal transition-colors motion-reduce:transition-none',
              'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25',
              'disabled:cursor-not-allowed disabled:opacity-50',
              selected
                ? 'border-foreground font-medium text-foreground'
                : 'border-transparent text-secondary-text hover:border-border hover:text-foreground',
            )}
            onClick={() => activate(item)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowRight') {
                event.preventDefault();
                move(index, 1);
              } else if (event.key === 'ArrowLeft') {
                event.preventDefault();
                move(index, -1);
              } else if (event.key === 'Home') {
                event.preventDefault();
                moveToEdge(false);
              } else if (event.key === 'End') {
                event.preventDefault();
                moveToEdge(true);
              }
            }}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
});

Tabs.displayName = 'Tabs';

export interface TabPanelProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'role'> {
  tabsId: string;
  value: string;
  activeValue: string;
}

export const TabPanel = forwardRef<
  HTMLDivElement,
  TabPanelProps
>(({
  tabsId,
  value,
  activeValue,
  className,
  children,
  ...props
}, ref) => (
  <div
    {...props}
    ref={ref}
    id={getTabPanelId(tabsId, value)}
    role="tabpanel"
    aria-labelledby={getTabId(tabsId, value)}
    tabIndex={0}
    hidden={value !== activeValue}
    data-pattern="tab-panel"
    className={cn('min-w-0 py-4 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25', className)}
  >
    {children}
  </div>
));

TabPanel.displayName = 'TabPanel';
