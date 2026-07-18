import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { InlineAlert } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { SETTINGS_MISC_TEXT } from '../../locales/settingsMisc';

interface SettingsPanelErrorBoundaryProps {
  title: string;
  children: ReactNode;
  resetKey?: string | number;
  className?: string;
  diagnosticHint?: ReactNode;
}

interface SettingsPanelErrorBoundaryLabels {
  loadFailedSuffix: string;
  runtimeErrorMessage: string;
  defaultDiagnosticHint: string;
  errorSummaryPrefix: string;
}

interface SettingsPanelErrorBoundaryState {
  hasError: boolean;
  errorSummary: string;
}

const MAX_ERROR_SUMMARY_LENGTH = 180;

function sanitizeUrlLikeText(value: string) {
  return value.replace(/https?:\/\/[^\s"'<>]+/gi, (match) => {
    try {
      const url = new URL(match);
      const sanitizedPath = url.pathname && url.pathname !== '/' ? '/[redacted]' : '';
      const sanitizedUrl = `${url.protocol}//${url.host}${sanitizedPath}`;
      return `${sanitizedUrl}${url.search ? '?[redacted]' : ''}${url.hash ? '#[redacted]' : ''}`;
    } catch {
      return match
        .replace(/^(https?:\/\/[^/?#\s"'<>]+)\/[^?#\s"'<>]*/i, '$1/[redacted]')
        .replace(/\?[^#\s"'<>]*/g, '?[redacted]')
        .replace(/#[^\s"'<>]*/g, '#[redacted]');
    }
  });
}

function getSafeErrorSummary(error: unknown) {
  const rawMessage = error instanceof Error
    ? error.message
    : typeof error === 'string'
      ? error
      : 'Unknown frontend runtime error';
  const normalized = rawMessage.replace(/\s+/g, ' ').trim() || 'Unknown frontend runtime error';
  const sanitized = sanitizeUrlLikeText(normalized)
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]{8,}/gi, 'Bearer [redacted]')
    .replace(/\b(sk-[A-Za-z0-9_-]{8,})\b/g, '[redacted-key]')
    .replace(
      /\b([A-Z0-9_]*(?:api[_-]?key|token|secret|password|passwd|authorization|webhook(?:_url)?)\s*[:=]\s*)([^\s,;'"`]+)/gi,
      '$1[redacted]'
    );

  if (sanitized.length <= MAX_ERROR_SUMMARY_LENGTH) {
    return sanitized;
  }

  return `${sanitized.slice(0, MAX_ERROR_SUMMARY_LENGTH)}...`;
}

class SettingsPanelErrorBoundaryImpl extends Component<
  SettingsPanelErrorBoundaryProps & { labels: SettingsPanelErrorBoundaryLabels },
  SettingsPanelErrorBoundaryState
> {
  override state: SettingsPanelErrorBoundaryState = {
    hasError: false,
    errorSummary: '',
  };

  static getDerivedStateFromError(error: unknown): SettingsPanelErrorBoundaryState {
    return {
      hasError: true,
      errorSummary: getSafeErrorSummary(error),
    };
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`Settings panel runtime error: ${this.props.title}`, error, errorInfo);
  }

  override componentDidUpdate(prevProps: SettingsPanelErrorBoundaryProps) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, errorSummary: '' });
    }
  }

  override render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className={cn('rounded-xl border settings-border bg-card/94 p-5 shadow-soft-card-strong backdrop-blur-sm', this.props.className)}>
        <InlineAlert
          title={`${this.props.title}${this.props.labels.loadFailedSuffix}`}
          variant="danger"
          message={(
            <div className="space-y-2">
              <p>
                {this.props.labels.runtimeErrorMessage}
              </p>
              {this.props.diagnosticHint ? (
                <p>{this.props.diagnosticHint}</p>
              ) : (
                <p>{this.props.labels.defaultDiagnosticHint}</p>
              )}
              {this.state.errorSummary ? (
                <p className="break-words font-mono text-xs opacity-80">
                  {this.props.labels.errorSummaryPrefix}{this.state.errorSummary}
                </p>
              ) : null}
            </div>
          )}
        />
      </div>
    );
  }
}

export const SettingsPanelErrorBoundary = (props: SettingsPanelErrorBoundaryProps) => {
  const { language } = useUiLanguage();
  const text = SETTINGS_MISC_TEXT[language];
  const labels: SettingsPanelErrorBoundaryLabels = {
    loadFailedSuffix: text.loadFailedSuffix,
    runtimeErrorMessage: text.runtimeError,
    defaultDiagnosticHint: text.diagnosticHint,
    errorSummaryPrefix: text.errorSummaryPrefix,
  };

  return <SettingsPanelErrorBoundaryImpl {...props} labels={labels} />;
};
