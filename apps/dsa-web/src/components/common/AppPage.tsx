import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface AppPageProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export const AppPage = forwardRef<HTMLDivElement, AppPageProps>(({
  children,
  className,
  ...props
}, ref) => {
  return (
    // div, not main: the app shell already renders the single <main> landmark.
    <div
      {...props}
      ref={ref}
      data-pattern="app-page"
      data-page-width="full"
      className={cn('mx-auto min-h-full w-full max-w-none px-4 pb-8 pt-4 md:px-6 lg:px-8', className)}
    >
      {children}
    </div>
  );
});

AppPage.displayName = 'AppPage';
