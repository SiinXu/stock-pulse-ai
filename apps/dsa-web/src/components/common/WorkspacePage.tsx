// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';
import { AppPage, type AppPageProps } from './AppPage';

export interface WorkspacePageProps extends AppPageProps {
  rail?: React.ReactNode;
  contentClassName?: string;
}

export const WorkspacePage = forwardRef<HTMLDivElement, WorkspacePageProps>(({
  children,
  rail,
  contentClassName,
  className,
  ...props
}, ref) => (
  <AppPage {...props} ref={ref} className={className}>
    <div
      data-pattern="workspace-page"
      className={cn(
        'min-w-0 gap-6',
        rail && 'grid xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]',
      )}
    >
      <div data-slot="workspace-content" className={cn('min-w-0', contentClassName)}>
        {children}
      </div>
      {rail ? <div data-slot="workspace-rail" className="min-w-0">{rail}</div> : null}
    </div>
  </AppPage>
));

WorkspacePage.displayName = 'WorkspacePage';
