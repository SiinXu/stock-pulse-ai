import type React from 'react';
import { Archive, ChevronDown } from 'lucide-react';
import { cn } from '../../utils/cn';

interface NotificationPanelProps extends React.HTMLAttributes<HTMLElement> {
  title: string;
  emptyText: string;
  filterLabel?: string;
  onFilterClick?: () => void;
}

export const NotificationPanel: React.FC<NotificationPanelProps> = ({
  title,
  emptyText,
  filterLabel,
  onFilterClick,
  className,
  ...props
}) => (
  <section
    className={cn(
      'flex min-h-57 w-67 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-soft-card-strong',
      className,
    )}
    {...props}
  >
    <header className="flex h-13 shrink-0 items-center justify-between border-b border-border px-3">
      <h2 className="text-base font-medium leading-6 tracking-normal text-foreground">{title}</h2>
      {filterLabel ? (
        <button
          type="button"
          className="notification-filter-button inline-flex h-7 items-center gap-1.5 border border-border bg-hover px-3 text-xs font-medium tracking-normal text-foreground dark:bg-border"
          onClick={onFilterClick}
        >
          {filterLabel}
          <ChevronDown className="h-2 w-2" aria-hidden="true" />
        </button>
      ) : null}
    </header>
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-4 pb-3 text-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-base text-muted-text dark:bg-border">
        <Archive className="h-4 w-4" aria-hidden="true" />
      </span>
      <p className="text-xs font-normal leading-[1.35] tracking-normal text-muted-text">
        {emptyText}
      </p>
    </div>
  </section>
);
