import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface StickyActionBarProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export const StickyActionBar = forwardRef<HTMLDivElement, StickyActionBarProps>(({ children, className, ...props }, ref) => {
  return (
    <div
      ref={ref}
      className={cn(
        'sticky bottom-0 border-t border-border bg-background/95 px-1 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur-sm',
        className,
      )}
      {...props}
    >
      <div className="flex flex-wrap items-center justify-end gap-2">{children}</div>
    </div>
  );
});

StickyActionBar.displayName = 'StickyActionBar';
