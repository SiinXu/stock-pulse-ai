import type React from 'react';
import { cn } from '../../utils/cn';

export interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  eyebrow,
  title,
  description,
  actions,
  className = '',
}) => {
  return (
    <header className={cn('py-1', className)}>
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          {eyebrow ? <span className="label-uppercase">{eyebrow}</span> : null}
          <h1 className="text-[1.75rem] font-semibold leading-tight tracking-normal text-foreground">{title}</h1>
          {description ? <p className="mt-1.5 max-w-2xl text-sm text-secondary-text">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
};
