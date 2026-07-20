// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { forwardRef, useCallback, useEffect, useId, useState } from 'react';
import { ChevronDown, PanelRightOpen } from 'lucide-react';
import { cn } from '../../utils/cn';
import { Drawer } from './Drawer';
import { IconButton } from './IconButton';

const TABLET_RAIL_QUERY = '(min-width: 768px) and (max-width: 1023px)';

function isTabletRailViewport(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(TABLET_RAIL_QUERY).matches;
}

export interface ResponsiveRailProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title: React.ReactNode;
  drawerTitle: string;
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
  drawerTitle,
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
  const [isTablet, setIsTablet] = useState(isTabletRailViewport);
  const isOpen = open ?? internalOpen;
  const railId = id ?? `responsive-rail-${generatedId}`;
  const headingId = `${railId}-heading`;
  const contentId = `${railId}-content`;

  const setOpen = useCallback((nextOpen: boolean) => {
    if (open === undefined) setInternalOpen(nextOpen);
    onOpenChange?.(nextOpen);
  }, [onOpenChange, open]);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const media = window.matchMedia(TABLET_RAIL_QUERY);
    const update = () => {
      if (isOpen) setOpen(false);
      setIsTablet(media.matches);
    };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [isOpen, setOpen]);

  return (
    <>
      <aside
        {...props}
        ref={ref}
        id={railId}
        aria-labelledby={headingId}
        data-pattern="responsive-rail"
        data-compact-state={isOpen ? 'expanded' : 'collapsed'}
        data-tablet-presentation={isTablet ? 'drawer' : 'inline'}
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
            aria-controls={isTablet && !isOpen ? undefined : contentId}
            size="default"
            variant="outline"
            tooltip={false}
            aria-haspopup={isTablet ? 'dialog' : undefined}
            className={isTablet ? undefined : 'md:hidden lg:inline-flex xl:hidden'}
            onClick={() => setOpen(!isOpen)}
          >
            {isTablet ? (
              <PanelRightOpen aria-hidden="true" className="h-4 w-4" />
            ) : (
              <ChevronDown
                aria-hidden="true"
                className={cn('h-4 w-4 transition-transform motion-reduce:transition-none', isOpen && 'rotate-180')}
              />
            )}
          </IconButton>
        </header>
        {!isTablet ? (
          <div
            id={contentId}
            data-slot="rail-content"
            className={cn('mt-3 min-w-0 xl:block', isOpen ? 'block' : 'hidden', contentClassName)}
          >
            {children}
          </div>
        ) : null}
      </aside>
      <Drawer
        isOpen={isTablet && isOpen}
        onClose={() => setOpen(false)}
        title={drawerTitle}
        variant="navigation"
      >
        <div
          id={contentId}
          data-slot="rail-content"
          className={cn('min-w-0 p-4', contentClassName)}
        >
          {children}
        </div>
      </Drawer>
    </>
  );
});

ResponsiveRail.displayName = 'ResponsiveRail';
