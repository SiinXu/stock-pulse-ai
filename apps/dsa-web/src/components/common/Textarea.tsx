import type React from 'react';
import { forwardRef, useId } from 'react';
import { cn } from '../../utils/cn';
import { Field } from './Field';
import { getFieldDescriptionIds } from './fieldDescription';

export type TextareaSize = 'default' | 'comfortable';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  fieldClassName?: string;
  size?: TextareaSize;
}

const TEXTAREA_SIZE_STYLES: Record<TextareaSize, string> = {
  default: 'min-h-20',
  comfortable: 'min-h-24',
};

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(({
  label,
  hint,
  error,
  fieldClassName,
  className,
  id,
  size = 'comfortable',
  ...props
}, ref) => {
  const generatedId = useId();
  const textareaId = id ?? props.name ?? generatedId;
  const { hintId, errorId, describedBy } = getFieldDescriptionIds(
    textareaId,
    hint,
    error,
    props['aria-describedby'],
  );

  return (
    <Field
      controlId={textareaId}
      label={label}
      hint={hint}
      error={error}
      hintId={hintId}
      errorId={errorId}
      className={fieldClassName}
    >
      <textarea
        {...props}
        ref={ref}
        id={textareaId}
        aria-describedby={describedBy}
        aria-invalid={props['aria-invalid'] ?? (error ? true : undefined)}
        data-control="textarea"
        data-size={size}
        className={cn(
          'w-full resize-y rounded-lg border border-border bg-transparent px-3 py-2 text-base text-foreground',
          'placeholder:text-muted-text transition-[color,background-color,border-color,box-shadow] duration-150 focus:border-muted-text focus:outline-none motion-reduce:transition-none sm:text-xs',
          'disabled:cursor-not-allowed disabled:opacity-60',
          TEXTAREA_SIZE_STYLES[size],
          error && 'border-danger/40 focus:border-danger',
          className,
        )}
      />
    </Field>
  );
});

Textarea.displayName = 'Textarea';
