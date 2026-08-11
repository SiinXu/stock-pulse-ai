// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { ShieldAlert, ShieldCheck, ShieldQuestion, ShieldX } from 'lucide-react';
import { Badge, InlineAlert, Spinner } from '../common';
import {
  buildDecisionActionLabelMap,
  getDecisionActionLabel,
} from '../../utils/decisionAction';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { DecisionAction, ReportLanguage } from '../../types/analysis';
import type { RiskGatePresentation, RiskGatePresentationStatus } from './reportRiskGateUtils';

export interface ReportRiskGateBannerProps {
  presentation: RiskGatePresentation;
  language?: ReportLanguage | string | null;
  compact?: boolean;
  className?: string;
}

type ReportText = ReturnType<typeof getReportText>;

const DECISION_ACTIONS = new Set<string>([
  'buy',
  'add',
  'hold',
  'reduce',
  'sell',
  'watch',
  'avoid',
  'alert',
]);

const statusTone = (
  status: RiskGatePresentationStatus,
): 'info' | 'success' | 'warning' | 'danger' => {
  switch (status) {
    case 'pass':
      return 'success';
    case 'downgrade':
      return 'warning';
    case 'reject':
      return 'danger';
    case 'error':
      return 'danger';
    case 'not_evaluated':
      return 'warning';
    case 'loading':
    default:
      return 'info';
  }
};

const statusBadgeVariant = (
  status: RiskGatePresentationStatus,
): 'default' | 'success' | 'warning' | 'danger' | 'info' => {
  switch (status) {
    case 'pass':
      return 'success';
    case 'downgrade':
      return 'warning';
    case 'reject':
      return 'danger';
    case 'error':
      return 'danger';
    case 'not_evaluated':
      return 'warning';
    case 'loading':
      return 'info';
    default:
      return 'default';
  }
};

const StatusIcon: React.FC<{ status: RiskGatePresentationStatus }> = ({ status }) => {
  const className = 'h-4 w-4 shrink-0';
  switch (status) {
    case 'pass':
      return <ShieldCheck className={className} aria-hidden="true" />;
    case 'downgrade':
      return <ShieldAlert className={className} aria-hidden="true" />;
    case 'reject':
      return <ShieldX className={className} aria-hidden="true" />;
    case 'loading':
      return <Spinner size="sm" className="shrink-0" />;
    case 'error':
    case 'not_evaluated':
    default:
      return <ShieldQuestion className={className} aria-hidden="true" />;
  }
};

const verdictLabel = (status: RiskGatePresentationStatus, text: ReportText): string => {
  switch (status) {
    case 'pass':
      return text.riskGateVerdictPass;
    case 'downgrade':
      return text.riskGateVerdictDowngrade;
    case 'reject':
      return text.riskGateVerdictReject;
    case 'not_evaluated':
      return text.riskGateNotEvaluated;
    case 'error':
      return text.riskGateError;
    case 'loading':
      return text.riskGateLoading;
    default:
      return text.riskGateNotEvaluated;
  }
};

const formatAction = (
  action: string | undefined,
  actionLabels: ReturnType<typeof buildDecisionActionLabelMap>,
): string | undefined => {
  if (!action) {
    return undefined;
  }
  const knownAction = DECISION_ACTIONS.has(action)
    ? (action as DecisionAction)
    : null;
  return (
    getDecisionActionLabel(knownAction, action, null, action, actionLabels)
    ?? action
  );
};

const CodeList: React.FC<{ label: string; codes: string[]; testId: string }> = ({
  label,
  codes,
  testId,
}) => {
  if (codes.length === 0) {
    return null;
  }
  return (
    <div data-testid={testId}>
      <p className="text-xs font-medium opacity-80">{label}</p>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {codes.map((code) => (
          <li key={code}>
            <Badge variant="default" size="sm" className="font-mono">
              {code}
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
};

/**
 * User-visible Risk Manager gate conclusion.
 * Reject is assertive (role=alert via InlineAlert danger + urgent).
 * Missing evaluation never renders as pass.
 */
export const ReportRiskGateBanner: React.FC<ReportRiskGateBannerProps> = ({
  presentation,
  language,
  compact = false,
  className = '',
}) => {
  const { t } = useUiLanguage();
  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);
  const actionLabels = buildDecisionActionLabelMap(t);
  const { status } = presentation;
  const tone = statusTone(status);
  const isReject = status === 'reject';
  const isNotEvaluated = status === 'not_evaluated';
  const isLoading = status === 'loading';
  const isError = status === 'error';

  const originalLabel = formatAction(presentation.originalAction, actionLabels);
  const finalLabel = formatAction(presentation.finalAction, actionLabels);
  const actionLine =
    originalLabel || finalLabel
      ? `${originalLabel ?? text.noValue} → ${finalLabel ?? text.noValue}`
      : undefined;

  let bodyMessage: string;
  if (isLoading) {
    bodyMessage = text.riskGateLoadingDescription;
  } else if (isError) {
    bodyMessage = text.riskGateErrorDescription;
  } else if (isNotEvaluated) {
    bodyMessage = text.riskGateNotEvaluatedDescription;
  } else if (isReject) {
    bodyMessage = text.riskGateRejectDescription;
  } else if (status === 'downgrade') {
    bodyMessage = text.riskGateDowngradeDescription;
  } else {
    bodyMessage = text.riskGatePassDescription;
  }

  return (
    <div
      className={className}
      data-testid="report-risk-gate-banner"
      data-risk-gate-status={status}
      data-risk-gate-reject={isReject ? 'true' : 'false'}
      data-risk-gate-not-evaluated={isNotEvaluated ? 'true' : 'false'}
    >
      <InlineAlert
        variant={tone}
        size={compact ? 'compact' : 'default'}
        urgent={isReject}
        title={text.riskGateHeading}
        message={(
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusIcon status={status} />
              <Badge
                variant={statusBadgeVariant(status)}
                size="sm"
                data-testid="report-risk-gate-verdict"
              >
                {verdictLabel(status, text)}
              </Badge>
            </div>
            <p data-testid="report-risk-gate-message">{bodyMessage}</p>

            {actionLine ? (
              <p className="text-sm" data-testid="report-risk-gate-actions">
                <span className="font-medium">{text.riskGateActionChange}: </span>
                <span className="font-mono">{actionLine}</span>
              </p>
            ) : null}

            {presentation.profile ? (
              <p className="text-sm" data-testid="report-risk-gate-profile">
                <span className="font-medium">{text.riskGateProfile}: </span>
                <span className="font-mono">{presentation.profile}</span>
              </p>
            ) : null}

            {presentation.failClosed ? (
              <p className="text-sm font-medium" data-testid="report-risk-gate-fail-closed">
                {text.riskGateFailClosed}
              </p>
            ) : null}

            {presentation.authorizedBypassId ? (
              <p className="text-sm" data-testid="report-risk-gate-bypass">
                <span className="font-medium">{text.riskGateBypass}: </span>
                <span className="font-mono">{presentation.authorizedBypassId}</span>
              </p>
            ) : null}

            <CodeList
              label={text.riskGateReasonCodes}
              codes={presentation.reasonCodes}
              testId="report-risk-gate-reasons"
            />
            <CodeList
              label={text.riskGateEvidenceCodes}
              codes={presentation.evidenceCodes}
              testId="report-risk-gate-evidence"
            />
          </div>
        )}
      />
    </div>
  );
};

export default ReportRiskGateBanner;
