import type React from 'react';
import { cn } from '../../utils/cn';

interface AppPageProps {
  children: React.ReactNode;
  className?: string;
}

export const AppPage: React.FC<AppPageProps> = ({ children, className = '' }) => {
  return (
    // div, not main: the app shell already renders the single <main> landmark.
    <div className={cn('mx-auto min-h-full w-full max-w-7xl px-4 pb-8 pt-4 md:px-6 lg:px-8', className)}>
      {children}
    </div>
  );
};
