import type React from 'react';
import { Component, Suspense } from 'react';
import type { ErrorInfo } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { Button } from '../common/Button';
import { Spinner } from '../common/Spinner';

type PageLoadingFallbackProps = {
  fullPage?: boolean;
};

export const PageLoadingFallback: React.FC<PageLoadingFallbackProps> = ({ fullPage = true }) => {
  const { t } = useUiLanguage();
  return (
    <div
      role="status"
      aria-live="polite"
      className={
        fullPage
          ? 'flex min-h-dvh items-center justify-center bg-base'
          : 'flex min-h-[60vh] items-center justify-center'
      }
    >
      <Spinner size="lg" />
      <span className="sr-only">{t('common.loading')}</span>
    </div>
  );
};

/** Non-textual nav frame shown before auth/status content. No copy. */
export const AppShellSkeleton: React.FC = () => (
  <div
    data-app-shell-skeleton=""
    aria-busy="true"
    className="h-dvh overflow-hidden bg-background"
  >
    <div
      data-shell-mobile-header="true"
      className="pointer-events-none fixed inset-x-0 top-0 z-40 flex min-w-0 items-center gap-3 px-3 pt-[max(0.75rem,env(safe-area-inset-top))] lg:hidden"
    >
      <span className="h-10 w-10 rounded-lg bg-card shadow-soft-card" />
      <span className="h-4 max-w-[8rem] flex-1 rounded bg-muted" />
    </div>
    <div className="mx-auto flex h-full w-full overflow-hidden">
      <aside
        data-shell-sidebar="true"
        className="sticky top-0 z-40 hidden h-full w-20 shrink-0 self-start bg-background px-2 py-4 lg:flex lg:flex-col lg:items-center lg:gap-3"
      >
        <span className="h-8 w-8 rounded-lg bg-muted" />
        <span className="h-8 w-8 rounded-lg bg-muted" />
        <span className="h-8 w-8 rounded-lg bg-muted" />
        <span className="h-8 w-8 rounded-lg bg-muted" />
      </aside>
      <div
        data-shell-main="true"
        className="relative mt-[calc(2.75rem+max(0.75rem,env(safe-area-inset-top)))] mb-3 mx-3 flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-soft-card lg:mt-4 lg:mb-4 lg:ml-1 lg:mr-4"
      />
    </div>
  </div>
);

type RouteErrorBoundaryProps = {
  children: React.ReactNode;
  resetKey: string;
  fullPage: boolean;
  text: {
    title: string;
    description: string;
    reload: string;
    backHome: string;
  };
};

type RouteErrorBoundaryState = {
  hasError: boolean;
};

class RouteErrorBoundary extends Component<RouteErrorBoundaryProps, RouteErrorBoundaryState> {
  override state: RouteErrorBoundaryState = {
    hasError: false,
  };

  static getDerivedStateFromError(): RouteErrorBoundaryState {
    return { hasError: true };
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Route page failed to render or load', error, errorInfo);
  }

  override componentDidUpdate(prevProps: RouteErrorBoundaryProps) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  override render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div
        className={
          this.props.fullPage
            ? 'flex min-h-dvh items-center justify-center bg-base px-4'
            : 'flex min-h-[60vh] items-center justify-center px-2 py-8'
        }
      >
        <div className="w-full max-w-sm rounded-lg border border-border bg-card/94 p-4 text-center shadow-soft-card">
          <h1 className="text-lg font-semibold text-foreground">{this.props.text.title}</h1>
          <p className="mt-2 text-sm leading-5 text-secondary-text">
            {this.props.text.description}
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <Button
              type="button"
              variant="primary"
              size="default"
              onClick={() => window.location.reload()}
            >
              {this.props.text.reload}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="default"
              onClick={() => window.location.assign('/')}
            >
              {this.props.text.backHome}
            </Button>
          </div>
        </div>
      </div>
    );
  }
}

export const RouteBoundary: React.FC<{ children: React.ReactNode; fullPage?: boolean }> = ({
  children,
  fullPage = true,
}) => {
  const location = useLocation();
  const { t } = useUiLanguage();
  const resetKey = `${location.pathname}${location.search}`;

  return (
    <RouteErrorBoundary
      resetKey={resetKey}
      fullPage={fullPage}
      text={{
        title: t('routeError.title'),
        description: t('routeError.description'),
        reload: t('routeError.reload'),
        backHome: t('routeError.backHome'),
      }}
    >
      <Suspense fallback={<PageLoadingFallback fullPage={fullPage} />}>{children}</Suspense>
    </RouteErrorBoundary>
  );
};

export const RouteOutletBoundary: React.FC = () => (
  <RouteBoundary fullPage={false}>
    <Outlet />
  </RouteBoundary>
);

export const StandaloneRouteBoundary: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <RouteBoundary fullPage>
    {children}
  </RouteBoundary>
);
