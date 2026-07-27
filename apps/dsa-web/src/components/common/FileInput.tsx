import type React from 'react';
import { forwardRef } from 'react';

export type FileInputProps = Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  'type' | 'className' | 'style' | 'children' | 'dangerouslySetInnerHTML'
>;

/** Hidden native file input paired with a visible shared control trigger. */
export const FileInput = forwardRef<HTMLInputElement, FileInputProps>((props, ref) => (
  <input
    {...props}
    ref={ref}
    type="file"
    data-control="file-input"
    className="hidden"
  />
));

FileInput.displayName = 'FileInput';
