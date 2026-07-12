import type React from 'react';
import { cn } from '../../utils/cn';

interface SettingsSectionCardProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentBordered?: boolean;
}

export const SettingsSectionCard: React.FC<SettingsSectionCardProps> = ({
  title,
  description,
  actions,
  children,
  className = '',
  contentBordered = false,
}) => {
  return (
    <section className={cn('rounded-2xl bg-card p-3 md:p-4', className)}>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h2 className="text-base font-semibold tracking-tight text-foreground">{title}</h2>
          {description ? <p className="text-sm leading-6 text-muted-text">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
      <div className={cn('space-y-4', contentBordered && 'rounded-xl border settings-border p-4')}>{children}</div>
    </section>
  );
};
