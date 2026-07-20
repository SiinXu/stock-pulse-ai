// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { SlidersHorizontal } from 'lucide-react';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Button } from './Button';
import { FilterSheet } from './Sheet';
import { Popover } from './Popover';

const DESKTOP_FILTER_QUERY = '(min-width: 48rem)';

function isDesktopFilterViewport(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(DESKTOP_FILTER_QUERY).matches;
}

export interface AdvancedFilterSheetProps {
  /** Visible label only; the Pattern renders activeCount separately. */
  triggerLabel: string;
  triggerAriaLabel: string;
  activeCount: number;
  title: string;
  description?: string;
  children: ReactNode;
  resetLabel: string;
  applyLabel: string;
  loadingLabel?: string;
  onReset: () => void;
  onApply: () => boolean | void;
  resetDisabled?: boolean;
  applyDisabled?: boolean;
  isApplying?: boolean;
  triggerDisabled?: boolean;
}

/** Desktop advanced-filter Popover with a mobile Bottom Sheet equivalent. */
export const AdvancedFilterSheet = ({
  triggerLabel,
  triggerAriaLabel,
  activeCount,
  title,
  description,
  children,
  resetLabel,
  applyLabel,
  loadingLabel,
  onReset,
  onApply,
  resetDisabled = false,
  applyDisabled = false,
  isApplying = false,
  triggerDisabled = false,
}: AdvancedFilterSheetProps) => {
  const [open, setOpen] = useState(false);
  const [isDesktop, setIsDesktop] = useState(isDesktopFilterViewport);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const popoverId = useId();
  const applyBlocked = applyDisabled || isApplying;

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const media = window.matchMedia(DESKTOP_FILTER_QUERY);
    const update = () => {
      setIsDesktop(media.matches);
      setOpen((wasOpen) => {
        if (wasOpen) requestAnimationFrame(() => triggerRef.current?.focus());
        return false;
      });
    };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  const setOpenSafely = (nextOpen: boolean) => {
    if (!nextOpen && isApplying) return;
    setOpen(nextOpen);
  };

  const apply = (close: () => void) => {
    if (applyBlocked) return;
    if (onApply() !== false) close();
  };

  const trigger = ({ open: triggerOpen, toggle }: { open: boolean; toggle: () => void }) => (
    <Button
      ref={triggerRef}
      type="button"
      variant="secondary"
      size="comfortable"
      disabled={triggerDisabled || isApplying}
      aria-label={triggerAriaLabel}
      aria-haspopup="dialog"
      aria-expanded={triggerOpen}
      aria-controls={triggerOpen && isDesktop ? popoverId : undefined}
      onClick={toggle}
    >
      <SlidersHorizontal aria-hidden="true" />
      {triggerLabel}
      {activeCount > 0 ? (
        <span
          className="inline-flex min-w-5 items-center justify-center rounded-full bg-foreground px-1.5 text-[0.6875rem] font-semibold text-background"
          aria-hidden="true"
        >
          {activeCount}
        </span>
      ) : null}
    </Button>
  );

  if (!isDesktop) {
    return (
      <>
        {trigger({ open, toggle: () => setOpenSafely(!open) })}
        <FilterSheet
          isOpen={open}
          onClose={() => setOpenSafely(false)}
          title={title}
          description={description}
          resetLabel={resetLabel}
          applyLabel={applyLabel}
          loadingLabel={loadingLabel}
          onReset={onReset}
          onApply={() => apply(() => setOpen(false))}
          resetDisabled={resetDisabled}
          applyDisabled={applyDisabled}
          isApplying={isApplying}
        >
          {children}
        </FilterSheet>
      </>
    );
  }

  return (
    <Popover
      open={open}
      onOpenChange={setOpenSafely}
      closeOnEscape={!isApplying}
      placement="bottom"
      align="end"
      contentRole="dialog"
      contentId={popoverId}
      ariaLabelledBy={titleId}
      contentClassName="w-96 max-w-[calc(100vw-2rem)]"
      trigger={trigger}
    >
      {({ close }) => (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            apply(close);
          }}
        >
          <header data-overlay-slot="header" className="border-b border-border px-4 py-3">
            <h2 id={titleId} className="text-sm font-semibold text-foreground">{title}</h2>
            {description ? <p className="mt-1 text-xs text-secondary-text">{description}</p> : null}
          </header>
          <div data-overlay-slot="body" className="max-h-[60dvh] space-y-3 overflow-y-auto p-4">
            {children}
          </div>
          <footer
            data-overlay-slot="footer"
            className="flex items-center justify-end gap-2 border-t border-border bg-elevated px-4 py-3"
          >
            <Button
              type="button"
              variant="ghost"
              size="comfortable"
              disabled={resetDisabled || isApplying}
              onClick={onReset}
            >
              {resetLabel}
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="comfortable"
              disabled={applyBlocked}
              isLoading={isApplying}
              loadingText={loadingLabel}
            >
              {applyLabel}
            </Button>
          </footer>
        </form>
      )}
    </Popover>
  );
};
