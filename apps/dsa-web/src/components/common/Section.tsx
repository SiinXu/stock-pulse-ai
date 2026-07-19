// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { forwardRef, useId } from 'react';
import { cn } from '../../utils/cn';

export interface SectionProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title?: React.ReactNode;
  description?: React.ReactNode;
  eyebrow?: React.ReactNode;
  actions?: React.ReactNode;
  headingAs?: 'h2' | 'h3' | 'h4';
  children: React.ReactNode;
}

export const Section = forwardRef<HTMLElement, SectionProps>(({
  title,
  description,
  eyebrow,
  actions,
  headingAs: Heading = 'h2',
  children,
  className,
  'aria-labelledby': ariaLabelledBy,
  ...props
}, ref) => {
  const generatedHeadingId = useId();
  const headingId = title ? generatedHeadingId : undefined;

  return (
    <section
      ref={ref}
      aria-labelledby={ariaLabelledBy ?? headingId}
      className={cn('min-w-0 space-y-4', className)}
      {...props}
    >
      {title || description || eyebrow || actions ? (
        <header className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            {eyebrow ? <div className="text-xs font-medium text-muted-text">{eyebrow}</div> : null}
            {title ? (
              <Heading id={headingId} className={cn('text-lg font-semibold text-foreground', eyebrow && 'mt-1')}>
                {title}
              </Heading>
            ) : null}
            {description ? <div className="mt-1 text-sm text-secondary-text">{description}</div> : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      <div className="min-w-0">{children}</div>
    </section>
  );
});

Section.displayName = 'Section';
