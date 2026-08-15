import React from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '../../utils/cn';

export function ChatThinkingToggle({
  isExpanded,
  summary,
  onToggle,
  thinkingProcessLabel,
}: {
  isExpanded: boolean;
  summary: string;
  onToggle: () => void;
  thinkingProcessLabel: string;
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={isExpanded}
      className="control-hit-target mb-2 flex w-full items-center gap-2 text-left text-xs text-muted-text transition-colors hover:text-secondary-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 motion-reduce:transition-none"
    >
      <ChevronRight
        className={cn(
          'h-3 w-3 shrink-0 transition-transform motion-reduce:transition-none',
          isExpanded && 'rotate-90',
        )}
        aria-hidden="true"
      />
      <span className="flex min-w-0 flex-wrap items-center gap-1.5">
        <span>{thinkingProcessLabel}</span>
        <span aria-hidden="true" className="text-muted-text/50">·</span>
        <span className="text-muted-text">{summary}</span>
      </span>
    </button>
  );
}
