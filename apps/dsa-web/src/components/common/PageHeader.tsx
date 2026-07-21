import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface PageHeaderProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  headingId?: string;
}

export const PageHeader = forwardRef<
  HTMLHeadingElement,
  PageHeaderProps
>(({
  eyebrow,
  title,
  description,
  actions,
  headingId,
  className,
  ...props
}, ref) => {
  return (
    <header {...props} data-pattern="page-header" className={cn('py-1', className)}>
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          {eyebrow ? <span className="label-uppercase">{eyebrow}</span> : null}
          <h1
            ref={ref}
            id={headingId}
            tabIndex={-1}
            className="break-words text-[1.75rem] font-semibold leading-tight tracking-normal text-foreground"
          >
            {title}
          </h1>
          {description ? <p className="mt-1.5 max-w-2xl text-sm text-secondary-text">{description}</p> : null}
        </div>
        {actions ? <div data-slot="actions" className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
});

PageHeader.displayName = 'PageHeader';
