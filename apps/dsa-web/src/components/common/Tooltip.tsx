import type React from 'react';
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';
import { getOverlayStyle } from './overlayZ';

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: 'top' | 'bottom';
  focusable?: boolean;
  className?: string;
  contentClassName?: string;
}

type TooltipStyle = {
  top: number;
  left: number;
};

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  side = 'top',
  focusable = false,
  className = '',
  contentClassName = '',
}) => {
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const tooltipRef = useRef<HTMLSpanElement | null>(null);
  const isHoveredRef = useRef(false);
  const isFocusedRef = useRef(false);
  const isEscapeDismissedRef = useRef(false);
  const tooltipId = useId();
  const describedElementRef = useRef<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  const [resolvedSide, setResolvedSide] = useState<'top' | 'bottom'>(side);
  const [style, setStyle] = useState<TooltipStyle>({ top: 0, left: 0 });

  const detachTooltipDescription = useCallback(() => {
    const target = describedElementRef.current;
    if (!target) {
      return;
    }

    const remainingIds = (target.getAttribute('aria-describedby') ?? '')
      .split(/\s+/)
      .filter((id) => id && id !== tooltipId);
    if (remainingIds.length > 0) {
      target.setAttribute('aria-describedby', remainingIds.join(' '));
    } else {
      target.removeAttribute('aria-describedby');
    }
    describedElementRef.current = null;
  }, [tooltipId]);

  const attachTooltipDescription = useCallback((target: HTMLElement) => {
    if (describedElementRef.current !== target) {
      detachTooltipDescription();
      describedElementRef.current = target;
    }

    const describedByIds = (target.getAttribute('aria-describedby') ?? '')
      .split(/\s+/)
      .filter(Boolean);
    if (!describedByIds.includes(tooltipId)) {
      target.setAttribute('aria-describedby', [...describedByIds, tooltipId].join(' '));
    }
  }, [detachTooltipDescription, tooltipId]);

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    const tooltip = tooltipRef.current;
    if (!trigger || !tooltip) {
      return;
    }

    const triggerRect = trigger.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const gap = 10;
    const margin = 8;

    let nextSide = side;
    let top =
      side === 'top'
        ? triggerRect.top - tooltipRect.height - gap
        : triggerRect.bottom + gap;

    if (side === 'top' && top < margin) {
      nextSide = 'bottom';
      top = triggerRect.bottom + gap;
    } else if (side === 'bottom' && top + tooltipRect.height > viewportHeight - margin) {
      nextSide = 'top';
      top = triggerRect.top - tooltipRect.height - gap;
    }

    let left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
    left = Math.max(margin, Math.min(left, viewportWidth - tooltipRect.width - margin));
    top = Math.max(margin, Math.min(top, viewportHeight - tooltipRect.height - margin));

    setResolvedSide(nextSide);
    setStyle({ top, left });
  }, [side]);

  useLayoutEffect(() => {
    if (!open) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      updatePosition();
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [open, content, updatePosition]);

  useEffect(() => {
    if (!open) {
      detachTooltipDescription();
      return;
    }

    const handleViewportChange = () => updatePosition();
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);

    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [detachTooltipDescription, open, updatePosition]);

  useEffect(() => () => detachTooltipDescription(), [detachTooltipDescription]);

  if (!content) {
    return <>{children}</>;
  }

  return (
    <>
      <span
        ref={triggerRef}
        className={cn('inline-flex', className)}
        onMouseEnter={() => {
          isHoveredRef.current = true;
          if (!isEscapeDismissedRef.current) {
            setOpen(true);
          }
        }}
        onMouseLeave={() => {
          isHoveredRef.current = false;
          setOpen(false);
          if (!isFocusedRef.current) {
            isEscapeDismissedRef.current = false;
          }
        }}
        onFocus={(event) => {
          isFocusedRef.current = true;
          attachTooltipDescription(event.target as HTMLElement);
          if (!isEscapeDismissedRef.current) {
            setOpen(true);
          }
        }}
        onBlur={() => {
          isFocusedRef.current = false;
          detachTooltipDescription();
          setOpen(false);
          if (!isHoveredRef.current) {
            isEscapeDismissedRef.current = false;
          }
        }}
        onKeyDown={(event) => {
          if (open && event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            isEscapeDismissedRef.current = true;
            detachTooltipDescription();
            setOpen(false);
          }
        }}
        tabIndex={focusable ? 0 : undefined}
        aria-describedby={focusable && open ? tooltipId : undefined}
        data-dialog-popup={open ? 'true' : undefined}
      >
        {children}
      </span>

      {typeof document !== 'undefined' && open
        ? createPortal(
            <span
              ref={tooltipRef}
              id={tooltipId}
              role="tooltip"
              style={getOverlayStyle('tooltip', {
                position: 'fixed',
                top: style.top,
                left: style.left,
              })}
              className={cn(
                'pointer-events-none min-w-max max-w-[18rem] rounded-xl border border-border/70 bg-elevated/95 px-3 py-1.5 text-xs leading-5 text-foreground shadow-xl backdrop-blur-sm',
                resolvedSide === 'top' ? 'origin-bottom' : 'origin-top',
                contentClassName,
              )}
            >
              {content}
            </span>,
            document.body,
          )
        : null}
    </>
  );
};
