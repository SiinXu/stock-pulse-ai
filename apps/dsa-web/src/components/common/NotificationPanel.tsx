import type React from 'react';
import { useId } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '../../utils/cn';
import { Button } from './Button';
import { StatePanel } from './StatePanel';

export interface NotificationPanelItem {
  id: React.Key;
  title: React.ReactNode;
  description?: React.ReactNode;
  meta?: React.ReactNode;
  leading?: React.ReactNode;
  unread?: boolean;
  onSelect?: () => void;
}

interface NotificationPanelProps extends React.HTMLAttributes<HTMLElement> {
  title: string;
  emptyText: string;
  items?: readonly NotificationPanelItem[];
  isLoading?: boolean;
  loadingText?: string;
  errorText?: string;
  retryLabel?: string;
  onRetry?: () => void;
  unreadLabel?: string;
  filterLabel?: string;
  onFilterClick?: () => void;
}

export const NotificationPanel: React.FC<NotificationPanelProps> = ({
  title,
  emptyText,
  items = [],
  isLoading = false,
  loadingText,
  errorText,
  retryLabel,
  onRetry,
  unreadLabel,
  filterLabel,
  onFilterClick,
  className,
  ...props
}) => {
  const titleId = useId();
  const panelState = isLoading ? 'loading' : errorText ? 'error' : items.length === 0 ? 'empty' : 'ready';

  return (
    <section
      aria-labelledby={titleId}
      data-state={panelState}
      className={cn(
        'flex min-h-57 w-67 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-soft-card-strong',
        className,
      )}
      {...props}
    >
      <header className="flex min-h-13 shrink-0 items-center justify-between gap-2 border-b border-border px-3">
        <h2 id={titleId} className="text-base font-medium leading-6 tracking-normal text-foreground">{title}</h2>
        {filterLabel ? (
          <button
            type="button"
            className="notification-filter-button inline-flex min-h-11 items-center gap-1.5 border border-transparent px-2 text-xs font-medium tracking-normal text-foreground transition-colors hover:bg-hover"
            onClick={onFilterClick}
          >
            {filterLabel}
            <ChevronDown className="h-3 w-3" aria-hidden="true" />
          </button>
        ) : null}
      </header>

      {isLoading ? (
        <StatePanel status="loading" title={loadingText ?? title} compact className="flex-1" />
      ) : errorText ? (
        <StatePanel
          status="error"
          title={errorText}
          compact
          className="flex-1"
          action={onRetry && retryLabel ? (
            <Button type="button" variant="ghost" size="sm" onClick={onRetry}>{retryLabel}</Button>
          ) : undefined}
        />
      ) : items.length === 0 ? (
        <StatePanel status="empty" title={emptyText} compact className="flex-1" />
      ) : (
        <ul className="flex-1 divide-y divide-border/60 overflow-y-auto" aria-live="polite">
          {items.map((item) => {
            const content = (
              <>
                {item.leading ? <span className="mt-0.5 shrink-0 text-secondary-text" aria-hidden="true">{item.leading}</span> : null}
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-foreground">
                    {item.title}
                    {item.unread && unreadLabel ? <span className="sr-only"> {unreadLabel}</span> : null}
                  </span>
                  {item.description ? <span className="mt-0.5 block text-xs text-secondary-text">{item.description}</span> : null}
                  {item.meta ? <span className="mt-1 block text-xs text-muted-text">{item.meta}</span> : null}
                </span>
                {item.unread ? <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" aria-hidden="true" /> : null}
              </>
            );

            return (
              <li key={item.id}>
                {item.onSelect ? (
                  <button
                    type="button"
                    className="flex min-h-11 w-full items-start gap-3 px-3 py-3 text-left transition-colors hover:bg-hover focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-foreground/15"
                    onClick={item.onSelect}
                  >
                    {content}
                  </button>
                ) : (
                  <div className="flex min-h-11 items-start gap-3 px-3 py-3">{content}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};
