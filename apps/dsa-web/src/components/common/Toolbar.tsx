import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface ToolbarProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'role'> {
  'aria-label': string;
  left?: React.ReactNode;
  right?: React.ReactNode;
}

export const Toolbar = forwardRef<
  HTMLDivElement,
  ToolbarProps
>(({
  left,
  right,
  className,
  ...props
}, ref) => {
  return (
    <div
      {...props}
      ref={ref}
      role="toolbar"
      data-pattern="toolbar"
      className={cn(
        'flex w-full min-w-0 flex-col gap-3 border-y border-border/60 py-3 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      {left ? <div data-slot="start" className="flex min-w-0 flex-wrap items-center gap-2">{left}</div> : null}
      {right ? <div data-slot="end" className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">{right}</div> : null}
    </div>
  );
});

Toolbar.displayName = 'Toolbar';
