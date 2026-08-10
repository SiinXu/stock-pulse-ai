import type React from 'react';
import { cn } from '../../utils/cn';

interface ScrollAreaProps {
  children: React.ReactNode;
  className?: string;
  viewportClassName?: string;
  testId?: string;
  viewportRef?: React.Ref<HTMLDivElement>;
  onScroll?: React.UIEventHandler<HTMLDivElement>;
}

export const ScrollArea: React.FC<ScrollAreaProps> = ({
  children,
  className,
  viewportClassName,
  testId,
  viewportRef,
  onScroll,
}) => {
  return (
    // Outer shell must shrink inside flex parents so the viewport can scroll
    // instead of expanding the page (mobile stock bar / history rails).
    <div className={cn('flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden', className)}>
      <div
        ref={viewportRef}
        data-testid={testId}
        onScroll={onScroll}
        className={cn(
          // h-full alone fails when the parent height is content-sized; min-h-0 +
          // flex-1 keep the viewport bounded so clientHeight < scrollHeight.
          // Do not add touch-pan-y (touch-action: pan-y): it suppresses
          // pinch-to-zoom inside every ScrollArea (chat, history, etc.).
          'min-h-0 flex-1 overflow-y-auto overscroll-contain custom-scrollbar',
          viewportClassName,
        )}
      >
        {children}
      </div>
    </div>
  );
};
