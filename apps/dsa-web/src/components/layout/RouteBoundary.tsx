import type React from 'react';
import { Component, Suspense } from 'react';
import type { ErrorInfo } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { Button } from '../common/Button';

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
      <div aria-hidden="true" className="h-8 w-8 animate-spin rounded-full border-2 border-primary/20 border-t-primary" />
      <span className="sr-only">{t('common.loading')}</span>
    </div>
  );
};

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
