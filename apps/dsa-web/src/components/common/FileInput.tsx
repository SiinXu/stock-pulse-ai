import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export type FileInputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'>;

/** Hidden native file input used with a visible, shared Button trigger. */
export const FileInput = forwardRef<HTMLInputElement, FileInputProps>(({
  className,
  ...props
}, ref) => (
  <input
    {...props}
    ref={ref}
    type="file"
    className={cn('hidden', className)}
  />
));

FileInput.displayName = 'FileInput';
