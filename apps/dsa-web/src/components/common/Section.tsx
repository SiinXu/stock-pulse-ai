import type React from 'react';
import { forwardRef, useId } from 'react';
import { cn } from '../../utils/cn';
import { Surface, type SurfaceLevel, type SurfacePadding } from './Surface';

type SectionHeading = 'h2' | 'h3' | 'h4';

export interface SectionProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title: string;
  description?: React.ReactNode;
  eyebrow?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  headingAs?: SectionHeading;
  headingId?: string;
  level?: Extract<SurfaceLevel, 'canvas' | 'section'>;
  padding?: SurfacePadding;
  contentClassName?: string;
}

export const Section = forwardRef<HTMLElement, SectionProps>(({
  title,
  description,
  eyebrow,
  actions,
  children,
  headingAs = 'h2',
  headingId,
  level = 'canvas',
  padding = 'none',
  contentClassName,
  className,
  id,
  'aria-labelledby': ariaLabelledBy,
  ...props
}, ref) => {
  const generatedId = useId();
  const resolvedHeadingId = headingId ?? `${id ?? generatedId}-heading`;
  const Heading = headingAs;

  return (
    <Surface
      {...props}
      ref={ref}
      as="section"
      id={id}
      level={level}
      padding={padding}
      aria-labelledby={ariaLabelledBy ?? resolvedHeadingId}
      data-pattern="section"
      className={className}
    >
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          {eyebrow ? <div className="label-uppercase">{eyebrow}</div> : null}
          <Heading id={resolvedHeadingId} className={cn('text-base font-semibold text-foreground', eyebrow && 'mt-1')}>
            {title}
          </Heading>
          {description ? <div className="mt-1 text-sm leading-6 text-secondary-text">{description}</div> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      <div className={cn('mt-4', contentClassName)}>{children}</div>
    </Surface>
  );
});

Section.displayName = 'Section';
