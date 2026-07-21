import type React from 'react';
import { cn } from '../../utils/cn';
import { Section } from '../common/Section';

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
    <Section
      title={title}
      description={description}
      actions={actions}
      level="section"
      padding="none"
      className={cn('p-3 md:p-4', className)}
      contentClassName={cn('space-y-4', contentBordered && 'rounded-xl border settings-border p-4')}
    >
      {children}
    </Section>
  );
};
