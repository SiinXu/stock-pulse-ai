import type React from 'react';
import { useId } from 'react';
import { cn } from '../../utils/cn';

export interface SegmentedControlOption<T extends string> {
  value: T;
  label: React.ReactNode;
  icon?: React.ReactNode;
  disabled?: boolean;
}

interface SegmentedControlProps<T extends string> {
  value: T;
  options: Array<SegmentedControlOption<T>>;
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
  getPanelId?: (value: T) => string | undefined;
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className,
  getPanelId,
}: SegmentedControlProps<T>) {
  const generatedId = useId();

  const moveSelection = (currentIndex: number, direction: 1 | -1) => {
    for (let offset = 1; offset <= options.length; offset += 1) {
      const nextIndex = (currentIndex + direction * offset + options.length) % options.length;
      const nextOption = options[nextIndex];
      if (!nextOption.disabled) {
        onChange(nextOption.value);
        requestAnimationFrame(() => {
          document.getElementById(`${generatedId}-${nextOption.value}`)?.focus();
        });
        return;
      }
    }
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        'segmented-control inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full p-1',
        className,
      )}
    >
      {options.map((option, index) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            id={`${generatedId}-${option.value}`}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={getPanelId?.(option.value)}
            tabIndex={selected ? 0 : -1}
            disabled={option.disabled}
            className={cn(
              'segmented-control-tab inline-flex min-h-6 shrink-0 items-center justify-center gap-1.5 px-3 py-1 text-xs leading-[1.35] tracking-normal transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/15',
              selected
                ? 'bg-card font-medium text-foreground shadow-soft-card dark:bg-border'
                : 'font-normal text-muted-text hover:text-foreground',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                event.preventDefault();
                moveSelection(index, 1);
              } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                event.preventDefault();
                moveSelection(index, -1);
              }
            }}
          >
            {option.icon ? <span className="flex h-4 w-4 items-center justify-center">{option.icon}</span> : null}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
