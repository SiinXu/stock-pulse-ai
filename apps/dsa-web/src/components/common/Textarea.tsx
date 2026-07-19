import type React from 'react';
import { forwardRef, useId } from 'react';
import { cn } from '../../utils/cn';
import { Field } from './Field';
import { getFieldDescriptionIds } from './fieldDescription';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  fieldClassName?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(({
  label,
  hint,
  error,
  fieldClassName,
  className,
  id,
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
        className={cn(
          'min-h-24 w-full resize-y rounded-lg border border-border bg-transparent px-3 py-2 text-base text-foreground',
          'placeholder:text-muted-text transition-colors duration-200 focus:border-muted-text focus:outline-none sm:text-xs',
          'disabled:cursor-not-allowed disabled:opacity-60',
          error && 'border-danger/40 focus:border-danger',
          className,
        )}
      />
    </Field>
  );
});

Textarea.displayName = 'Textarea';
