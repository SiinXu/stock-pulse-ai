import type React from 'react';
import { ListTree } from 'lucide-react';
import type { AnalysisReport, AnalysisResult, DecisionAction } from '../../types/analysis';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { buildDecisionActionLabelMap, getDecisionActionLabel } from '../../utils/decisionAction';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import { Badge, Button, Surface } from '../common';

interface BeginnerReportSummaryProps {
  data: AnalysisResult | AnalysisReport;
  onShowProfessional: () => void;
}

type BeginnerRisk = 'elevated' | 'moderate' | 'unrated';

const ELEVATED_RISK_ACTIONS = new Set<DecisionAction>(['reduce', 'sell', 'avoid', 'alert']);
const MODERATE_RISK_ACTIONS = new Set<DecisionAction>(['buy', 'add', 'hold', 'watch']);

function resolveBeginnerRisk(action?: DecisionAction | null): BeginnerRisk {
  if (action && ELEVATED_RISK_ACTIONS.has(action)) return 'elevated';
  if (action && MODERATE_RISK_ACTIONS.has(action)) return 'moderate';
  return 'unrated';
}

const BeginnerReportSummary: React.FC<BeginnerReportSummaryProps> = ({
  data,
  onShowProfessional,
}) => {
  const { t } = useUiLanguage();
  const report = 'report' in data ? data.report : data;
  const reportText = getReportText(normalizeReportLanguage(report.meta.reportLanguage));
  const actionLabels = buildDecisionActionLabelMap(t);
  const conclusion = report.summary.analysisSummary?.trim() || reportText.noAnalysisSummary;
  const nextStep = report.summary.operationAdvice?.trim()
    || report.summary.actionLabel?.trim()
    || (report.summary.action
      ? getDecisionActionLabel(report.summary.action, null, null, reportText.noAdvice, actionLabels)
      : reportText.noAdvice);
  const risk = resolveBeginnerRisk(report.summary.action);
  const riskLabel = risk === 'elevated'
    ? t('home.beginnerRiskElevated')
    : risk === 'moderate'
      ? t('home.beginnerRiskModerate')
      : t('home.beginnerRiskUnrated');

  return (
    <Surface
      as="article"
      level="section"
      padding="md"
      className="space-y-5"
      data-testid="beginner-report-summary"
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-4">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-text">{t('home.beginnerSummaryTitle')}</p>
          <h2 className="mt-1 break-words text-lg font-semibold text-foreground">
            {report.meta.stockName || report.meta.stockCode}
          </h2>
          <p className="mt-1 font-mono text-xs text-secondary-text">{report.meta.stockCode}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-text">{t('home.beginnerRiskLevel')}</span>
          <Badge variant={risk === 'elevated' ? 'danger' : risk === 'moderate' ? 'warning' : 'default'}>
            {riskLabel}
          </Badge>
        </div>
      </header>

      <section aria-labelledby="beginner-conclusion-heading">
        <h3 id="beginner-conclusion-heading" className="text-sm font-semibold text-foreground">
          {t('home.beginnerConclusion')}
        </h3>
        <p className="mt-2 max-w-[72ch] whitespace-pre-wrap text-sm leading-6 text-secondary-text">
          {conclusion}
        </p>
      </section>

      <section aria-labelledby="beginner-next-step-heading">
        <h3 id="beginner-next-step-heading" className="text-sm font-semibold text-foreground">
          {t('home.beginnerNextStep')}
        </h3>
        <p className="mt-2 max-w-[72ch] whitespace-pre-wrap text-sm leading-6 text-secondary-text">
          {nextStep}
        </p>
      </section>

      <div className="flex justify-end border-t border-border pt-4">
        <Button type="button" variant="secondary" size="default" onClick={onShowProfessional}>
          <ListTree className="h-4 w-4" aria-hidden="true" />
          {t('home.showProfessionalDetails')}
        </Button>
      </div>
    </Surface>
  );
};

export default BeginnerReportSummary;
