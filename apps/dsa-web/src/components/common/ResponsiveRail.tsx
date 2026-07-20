// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { forwardRef, useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '../../utils/cn';
import { IconButton } from './IconButton';

export interface ResponsiveRailProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title: React.ReactNode;
  children: React.ReactNode;
  expandLabel: string;
  collapseLabel: string;
  actions?: React.ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  contentClassName?: string;
}

export const ResponsiveRail = forwardRef<
  HTMLElement,
  ResponsiveRailProps
>(({
  title,
  children,
  expandLabel,
  collapseLabel,
  actions,
  open,
  defaultOpen = false,
  onOpenChange,
  contentClassName,
  className,
  id,
  ...props
}, ref) => {
  const generatedId = useId();
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const isOpen = open ?? internalOpen;
  const railId = id ?? `responsive-rail-${generatedId}`;
  const headingId = `${railId}-heading`;
  const contentId = `${railId}-content`;

  const setOpen = (nextOpen: boolean) => {
    if (open === undefined) setInternalOpen(nextOpen);
    onOpenChange?.(nextOpen);
  };

  return (
    <aside
      {...props}
      ref={ref}
      id={railId}
      aria-labelledby={headingId}
      data-pattern="responsive-rail"
      data-compact-state={isOpen ? 'expanded' : 'collapsed'}
      className={cn(
        'min-w-0 border-t border-border pt-4 xl:sticky xl:top-4 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0',
        className,
      )}
    >
      <header className="flex min-h-9 min-w-0 items-center gap-2">
        <h2 id={headingId} className="min-w-0 flex-1 break-words text-sm font-semibold tracking-normal text-foreground">
          {title}
        </h2>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        <IconButton
          aria-label={isOpen ? collapseLabel : expandLabel}
          aria-expanded={isOpen}
          aria-controls={contentId}
          size="navigation"
          variant="outline"
          className="xl:hidden"
          onClick={() => setOpen(!isOpen)}
        >
          <ChevronDown
            aria-hidden="true"
            className={cn('h-4 w-4 transition-transform motion-reduce:transition-none', isOpen && 'rotate-180')}
          />
        </IconButton>
      </header>
      <div
        id={contentId}
        data-slot="rail-content"
        className={cn('mt-3 min-w-0 xl:block', isOpen ? 'block' : 'hidden', contentClassName)}
      >
        {children}
      </div>
    </aside>
  );
});

ResponsiveRail.displayName = 'ResponsiveRail';
