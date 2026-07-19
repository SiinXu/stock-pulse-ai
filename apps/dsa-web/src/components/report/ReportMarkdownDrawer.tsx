import type React from 'react';
import { Component, lazy, Suspense, useCallback, useMemo, useState } from 'react';
import { TriangleAlert } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { REPORT_CHROME_TEXT } from '../../locales/reportChrome';
import type { ReportLanguage } from '../../types/analysis';
import { Drawer } from '../common/Drawer';
import { Button } from '../common/Button';
import { Spinner } from '../common/Spinner';
import { OVERLAY_Z } from '../common/overlayZ';

interface ReportMarkdownDrawerProps {
  recordId: number;
  stockName: string;
  stockCode: string;
  onClose: () => void;
  reportLanguage?: ReportLanguage;
}

interface ReportMarkdownDrawerErrorBoundaryProps {
  resetKey: number;
  fallback: React.ReactNode;
  children: React.ReactNode;
}

interface ReportMarkdownDrawerErrorBoundaryState {
  hasError: boolean;
}

class ReportMarkdownDrawerErrorBoundary extends Component<
  ReportMarkdownDrawerErrorBoundaryProps,
  ReportMarkdownDrawerErrorBoundaryState
> {
  state: ReportMarkdownDrawerErrorBoundaryState = {
    hasError: false,
  };

  static getDerivedStateFromError(): ReportMarkdownDrawerErrorBoundaryState {
    return { hasError: true };
  }

  componentDidUpdate(prevProps: ReportMarkdownDrawerErrorBoundaryProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  componentDidCatch(error: unknown) {
    console.error('Report markdown drawer failed:', error);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }

    return this.props.children;
  }
}

const ReportMarkdownLoadingState: React.FC<{ message: string }> = ({ message }) => (
  <div className="flex h-64 flex-col items-center justify-center">
    <Spinner size="lg" />
    <p className="mt-4 text-sm text-secondary-text">{message}</p>
  </div>
);

const ReportMarkdownChunkErrorState: React.FC<{
  message: string;
  dismissText: string;
  onRequestClose: () => void;
}> = ({ message, dismissText, onRequestClose }) => (
  <div className="flex h-64 flex-col items-center justify-center">
    <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-danger/10">
      <TriangleAlert className="h-6 w-6 text-danger" aria-hidden="true" />
    </div>
    <p className="text-sm text-danger">{message}</p>
    <Button
      type="button"
      variant="secondary"
      size="md"
      onClick={onRequestClose}
      className="mt-4 min-h-11"
    >
      {dismissText}
    </Button>
  </div>
);

export const ReportMarkdownDrawer: React.FC<ReportMarkdownDrawerProps> = ({
  recordId,
  stockName,
  stockCode,
  onClose,
  reportLanguage = 'zh',
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const [isOpen, setIsOpen] = useState(true);
  const text = REPORT_CHROME_TEXT[uiLanguage];
  const LazyReportMarkdownPanel = useMemo(
    () => lazy(() => import('./ReportMarkdownPanel').then((m) => ({ default: m.ReportMarkdownPanel }))),
    [],
  );

  const handleClose = useCallback(() => {
    setIsOpen(false);
    setTimeout(onClose, 300);
  }, [onClose]);

  return (
    <Drawer
      isOpen={isOpen}
      onClose={handleClose}
      title={text.fullReport}
      width="max-w-3xl"
      zIndex={OVERLAY_Z.reportDrawer}
      backdropClassName="bg-background/56 backdrop-blur-[2px]"
    >
      <ReportMarkdownDrawerErrorBoundary
        resetKey={recordId}
        fallback={(
          <ReportMarkdownChunkErrorState
            message={text.loadReportFailed}
            dismissText={text.dismiss}
            onRequestClose={handleClose}
          />
        )}
      >
        <Suspense fallback={<ReportMarkdownLoadingState message={text.loadingReport} />}>
          <LazyReportMarkdownPanel
            recordId={recordId}
            stockName={stockName}
            stockCode={stockCode}
            reportLanguage={reportLanguage}
            onRequestClose={handleClose}
          />
        </Suspense>
      </ReportMarkdownDrawerErrorBoundary>
    </Drawer>
  );
};
