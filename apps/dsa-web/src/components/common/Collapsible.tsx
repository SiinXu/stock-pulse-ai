import React, { useId, useState } from 'react';
import { cn } from '../../utils/cn';

interface CollapsibleProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  /** Controlled open state. When omitted, the panel is uncontrolled. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  icon?: React.ReactNode;
  /** Optional subtitle kept visible while collapsed. */
  description?: React.ReactNode;
  /** Optional collapsed-header extras such as status badges. */
  trailing?: React.ReactNode;
  className?: string;
}

/**
 * Collapsible panel with animated expand and collapse behavior.
 */
export const Collapsible: React.FC<CollapsibleProps> = ({
  title,
  children,
  defaultOpen = false,
  open,
  onOpenChange,
  icon,
  description,
  trailing,
  className = '',
}) => {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : uncontrolledOpen;
  const panelId = useId();

  const setOpen = (next: boolean) => {
    if (!isControlled) {
      setUncontrolledOpen(next);
    }
    onOpenChange?.(next);
  };

  return (
    <div
      className={cn(
        'overflow-hidden rounded-xl border border-subtle bg-card/70 shadow-soft-card transition-all duration-300',
        'hover:border-accent',
        className,
      )}
    >
      <button
        type="button"
        onClick={() => setOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-controls={panelId}
        aria-label={title}
        className="flex min-h-11 w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-hover"
      >
        <div className="flex min-w-0 items-center gap-3">
          {icon && <span className="text-primary">{icon}</span>}
          <span className="min-w-0">
            <span className="font-medium text-foreground">{title}</span>
            {description ? (
              <span className="mt-1 block text-xs leading-5 text-muted-text">{description}</span>
            ) : null}
          </span>
        </div>
        <span className="flex shrink-0 items-center gap-2">
          {trailing}
          <svg
            className={cn('h-5 w-5 text-secondary-text transition-transform duration-300', isOpen && 'rotate-180')}
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </button>

      <div
        id={panelId}
        hidden={!isOpen}
        inert={isOpen ? undefined : true}
        className={cn(
          'grid transition-[grid-template-rows,opacity] duration-300 ease-in-out',
          isOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
        )}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="border-t border-subtle px-4 pb-4 pt-2">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};
