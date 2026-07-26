import type React from 'react';
import { cn } from '../../utils/cn';

export type ProgressTone = 'foreground' | 'primary';

export interface ProgressProps {
  value?: number;
  max?: number;
  label: string;
  valueText?: string;
  tone?: ProgressTone;
  className?: string;
}

export const Progress: React.FC<ProgressProps> = ({
  value,
  max = 100,
  label,
  valueText,
  tone = 'foreground',
  className,
}) => {
  const isDeterminate = typeof value === 'number' && Number.isFinite(value);
  const safeMax = max > 0 && Number.isFinite(max) ? max : 100;
  const safeValue = isDeterminate ? Math.min(Math.max(value, 0), safeMax) : undefined;
  const percentage = safeValue === undefined ? undefined : (safeValue / safeMax) * 100;

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={isDeterminate ? 0 : undefined}
      aria-valuemax={isDeterminate ? safeMax : undefined}
      aria-valuenow={safeValue}
      aria-valuetext={valueText}
      data-control="progress"
      className={cn('h-2 w-full overflow-hidden rounded-full bg-hover', className)}
    >
      <span
        aria-hidden="true"
        className={cn(
          'block h-full rounded-full transition-[width] duration-300 motion-reduce:transition-none',
          tone === 'primary' ? 'bg-primary' : 'bg-foreground',
          percentage === undefined && 'w-1/3 animate-pulse motion-reduce:animate-none',
        )}
        style={percentage === undefined ? undefined : { width: `${percentage}%` }}
      />
    </div>
  );
};
