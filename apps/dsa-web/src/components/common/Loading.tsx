import type React from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { Spinner } from './Spinner';

interface LoadingProps {
  label?: string;
  className?: string;
}

export const Loading: React.FC<LoadingProps> = ({ label, className = '' }) => {
  const { t } = useUiLanguage();

  return (
    <div role="status" aria-live="polite" className={cn('flex items-center justify-center p-8', className)}>
      <div className="inline-flex items-center gap-2 rounded-xl border border-border/60 bg-card px-4 py-2 text-sm text-secondary-text shadow-soft-card">
        <Spinner size="sm" className="text-primary" />
        {label ?? t('common.loading')}
      </div>
    </div>
  );
};
