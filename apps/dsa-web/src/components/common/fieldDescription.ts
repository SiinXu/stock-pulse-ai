import type React from 'react';

export interface FieldDescriptionIds {
  hintId?: string;
  errorId?: string;
  describedBy?: string;
}

export function getFieldDescriptionIds(
  controlId: string,
  hint: React.ReactNode,
  error: React.ReactNode,
  ariaDescribedBy?: string,
): FieldDescriptionIds {
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [ariaDescribedBy, errorId ?? hintId].filter(Boolean).join(' ') || undefined;
  return { hintId, errorId, describedBy };
}
