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

export interface WorkspaceLayoutProps {
  children: React.ReactNode;
  rail?: React.ReactNode;
  railPosition?: 'start' | 'end';
}

interface WorkspaceLayoutBaseProps extends WorkspaceLayoutProps {
  contentClassName?: string;
  pattern: 'workspace-layout' | 'workspace-page';
}

const WorkspaceLayoutBase = forwardRef<HTMLDivElement, WorkspaceLayoutBaseProps>(({
  children,
  rail,
  railPosition = 'end',
  pattern,
  contentClassName,
}, ref) => (
  <div
    ref={ref}
    data-pattern={pattern}
    data-rail-position={rail ? railPosition : undefined}
    className={cn(
      'min-w-0 gap-6',
      rail && (
        railPosition === 'start'
          ? 'grid xl:grid-cols-[minmax(14rem,18rem)_minmax(0,1fr)]'
          : 'grid xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]'
      ),
    )}
  >
    {rail && railPosition === 'start' ? (
      <div data-slot="workspace-rail" className="min-w-0">{rail}</div>
    ) : null}
    <div data-slot="workspace-content" className={cn('min-w-0', contentClassName)}>
      {children}
    </div>
    {rail && railPosition === 'end' ? (
      <div data-slot="workspace-rail" className="min-w-0">{rail}</div>
    ) : null}
  </div>
));

WorkspaceLayoutBase.displayName = 'WorkspaceLayoutBase';

export const WorkspaceLayout = forwardRef<HTMLDivElement, WorkspaceLayoutProps>((props, ref) => (
  <WorkspaceLayoutBase {...props} ref={ref} pattern="workspace-layout" />
));

WorkspaceLayout.displayName = 'WorkspaceLayout';

export const WorkspacePage = forwardRef<HTMLDivElement, WorkspacePageProps>(({
  children,
  rail,
  contentClassName,
  className,
  ...props
}, ref) => (
  <AppPage {...props} ref={ref} className={className}>
    <WorkspaceLayoutBase
      pattern="workspace-page"
      rail={rail}
      contentClassName={contentClassName}
    >
      {children}
    </WorkspaceLayoutBase>
  </AppPage>
));

WorkspacePage.displayName = 'WorkspacePage';
