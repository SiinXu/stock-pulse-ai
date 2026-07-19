import React from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { StatePanel } from './StatePanel';

interface LoadingProps {
  label?: string;
  className?: string;
}

export const Loading: React.FC<LoadingProps> = ({ label, className = '' }) => {
  const { t } = useUiLanguage();

  return (
    <StatePanel
      state="loading"
      title={label ?? t('common.loading')}
      titleAs="p"
      size="compact"
      className={className}
    />
  );
};
