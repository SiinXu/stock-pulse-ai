import type React from 'react';
import { StatePanel } from '../common/StatePanel';

interface DashboardStateBlockProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  compact?: boolean;
  loading?: boolean;
  titleAs?: 'p' | 'h2' | 'h3' | 'h4' | 'span';
}

export const DashboardStateBlock: React.FC<DashboardStateBlockProps> = ({
  title,
  description,
  icon,
  action,
  className = '',
  compact = false,
  loading = false,
  titleAs = 'p',
}) => {
  return (
    <StatePanel
      state={loading ? 'loading' : 'empty'}
      title={title}
      description={description}
      icon={loading ? undefined : icon}
      action={action}
      className={className}
      size={compact ? 'compact' : 'default'}
      titleAs={titleAs}
    />
  );
};
