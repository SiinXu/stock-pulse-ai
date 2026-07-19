import { forwardRef } from 'react';
import type React from 'react';
import { Search } from 'lucide-react';
import { cn } from '../../utils/cn';

interface SearchInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  wrapperClassName?: string;
  shortcut?: string;
}

export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(({
  className,
  wrapperClassName,
  shortcut,
  ...props
}, ref) => (
  <div
    className={cn(
      'flex h-11 min-w-0 items-center gap-2 rounded-lg border border-border bg-card px-2 shadow-soft-card sm:h-7',
      'focus-within:border-muted-text/50 focus-within:ring-2 focus-within:ring-foreground/10 dark:bg-base',
      wrapperClassName,
    )}
  >
    <Search className="h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />
    <input
      ref={ref}
      type="search"
      className={cn(
        'h-full min-w-0 flex-1 bg-transparent text-base leading-[1.35] tracking-normal text-foreground outline-none placeholder:text-muted-text sm:text-xs',
        'disabled:cursor-not-allowed disabled:opacity-60',
        className,
      )}
      {...props}
    />
    {shortcut ? (
      <kbd className="flex h-5 min-w-5 items-center justify-center rounded bg-hover px-1 text-sm font-medium leading-none text-muted-text dark:bg-card">
        {shortcut}
      </kbd>
    ) : null}
  </div>
));

SearchInput.displayName = 'SearchInput';
