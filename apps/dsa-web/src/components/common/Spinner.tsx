import type React from 'react';
import { cn } from '../../utils/cn';

export type SpinnerSize = 'sm' | 'md' | 'lg';

export interface SpinnerProps extends Omit<
  React.SVGAttributes<SVGSVGElement>,
  'children' | 'role' | 'aria-label' | 'aria-hidden'
> {
  size?: SpinnerSize;
  label?: string;
}

const SPINNER_SIZE_STYLES: Record<SpinnerSize, string> = {
  sm: 'h-4 w-4',
  md: 'h-5 w-5',
  lg: 'h-6 w-6',
};

/**
 * Shared loading indicator. Pass a label only when the spinner owns the
 * loading announcement; keep it decorative inside an existing busy control.
 */
export const Spinner: React.FC<SpinnerProps> = ({
  size = 'md',
  label,
  className,
  ...props
}) => (
  <svg
    {...props}
    data-control="spinner"
    role={label ? 'status' : undefined}
    aria-label={label}
    aria-hidden={label ? undefined : true}
    className={cn(
      'animate-spin text-current motion-reduce:animate-none',
      SPINNER_SIZE_STYLES[size],
      className,
    )}
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
    />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    />
  </svg>
);
