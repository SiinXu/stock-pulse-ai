import type React from 'react';
import { CalendarDays, ClipboardCheck, TrendingUp } from 'lucide-react';
import type {
  ReportDetails as ReportDetailsType,
  ReportMeta,
  ReportSummary as ReportSummaryType,
} from '../../types/analysis';
import { Badge, Button, Card, ScoreGauge } from '../common';
import { formatDateTime } from '../../utils/format';
import { getMarketPhaseSummaryLabel, getPartialBarLabel } from '../../utils/marketPhase';
import { normalizeBoardType } from '../../utils/reportDomain';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { buildDecisionActionLabelMap, getDecisionActionLabel } from '../../utils/decisionAction';

interface ReportOverviewProps {
  meta: ReportMeta;
  summary: ReportSummaryType;
  details?: ReportDetailsType;
  isHistory?: boolean;
  watchlist?: {
    isInWatchlist: (code: string) => boolean;
    onToggle: (code: string) => void;
    isActioning: boolean;
    actionMessage: string | null;
  };
}

type BoardStatus = 'leading' | 'lagging';

type BoardSignal = {
  status: BoardStatus;
  changePct?: number;
};

type BoardSignalMaps = {
  sectors: Map<string, BoardSignal>;
  concepts: Map<string, BoardSignal>;
};

type PreparedBoard = {
  key: string;
  name: string;
  signal?: BoardSignal;
};

const normalizeBoardName = (value?: string): string =>
  (value || '').trim().replace(/\s+/g, ' ');

const coerceFiniteNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim().replace(/%$/, '');
    if (!trimmed) {
      return undefined;
    }
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const buildRankingSignalMap = (rankings?: ReportDetailsType['sectorRankings']): Map<string, BoardSignal> => {
  const signalMap = new Map<string, BoardSignal>();
  const topBoards = Array.isArray(rankings?.top) ? rankings.top : [];
  const bottomBoards = Array.isArray(rankings?.bottom) ? rankings.bottom : [];

  topBoards.forEach((item) => {
    const normalizedName = normalizeBoardName(item?.name);
    const changePct = coerceFiniteNumber(item?.changePct);
    if (!normalizedName || changePct === undefined) {
      return;
    }
    signalMap.set(normalizedName, {
      status: 'leading',
      changePct,
    });
  });

  bottomBoards.forEach((item) => {
    const normalizedName = normalizeBoardName(item?.name);
    const changePct = coerceFiniteNumber(item?.changePct);
    if (!normalizedName || changePct === undefined) {
      return;
    }
    signalMap.set(normalizedName, {
      status: 'lagging',
      changePct,
    });
  });

  return signalMap;
};

const buildBoardSignalMaps = (details?: ReportDetailsType): BoardSignalMaps => ({
  sectors: buildRankingSignalMap(details?.sectorRankings),
  concepts: buildRankingSignalMap(details?.conceptRankings),
});

const resolveBoardSignal = (
  board: { name?: string; type?: string },
  signalMaps: BoardSignalMaps,
): BoardSignal | undefined => {
  const boardName = normalizeBoardName(board.name);
  if (!boardName) {
    return undefined;
  }
  const boardType = normalizeBoardType(board.type);
  if (boardType === 'sector') {
    return signalMaps.sectors.get(boardName);
  }
  if (boardType === 'concept') {
    return signalMaps.concepts.get(boardName);
  }
  const sectorSignal = signalMaps.sectors.get(boardName);
  const conceptSignal = signalMaps.concepts.get(boardName);
  if (sectorSignal && !conceptSignal) {
    return sectorSignal;
  }
  if (conceptSignal && !sectorSignal) {
    return conceptSignal;
  }
  return undefined;
};

const buildPreparedRelatedBoards = (
  boards: ReportDetailsType['belongBoards'],
  signalMaps: BoardSignalMaps,
): PreparedBoard[] => {
  if (!Array.isArray(boards)) {
    return [];
  }

  return boards.reduce<PreparedBoard[]>((preparedBoards, board, index) => {
    const boardName = normalizeBoardName(board?.name);
    if (!boardName) {
      return preparedBoards;
    }
    preparedBoards.push({
      key: `${boardName}-${board?.code || index}`,
      name: boardName,
      signal: resolveBoardSignal(board, signalMaps),
    });
    return preparedBoards;
  }, []);
};

/**
 * 报告概览区组件 - 终端风格
 */
export const ReportOverview: React.FC<ReportOverviewProps> = ({
  meta,
  summary,
  details,
  watchlist,
}) => {
  const { language, t } = useUiLanguage();
  const reportLanguage = normalizeReportLanguage(meta.reportLanguage);
  const text = getReportText(reportLanguage);
  const marketPhaseLabel = getMarketPhaseSummaryLabel(meta.marketPhaseSummary, reportLanguage);
  const partialBarLabel = meta.marketPhaseSummary?.isPartialBar === true
    ? getPartialBarLabel(reportLanguage)
    : null;
  const operationAdvice = summary.operationAdvice?.trim() || '';
  const canonicalActionLabel = getDecisionActionLabel(
    summary.action,
    summary.actionLabel,
    operationAdvice,
    operationAdvice || text.noAdvice,
    buildDecisionActionLabelMap(t),
  ) || text.noAdvice;
  const supportingAdvice = operationAdvice && operationAdvice !== canonicalActionLabel
    ? operationAdvice
    : null;
  const relatedBoards = (Array.isArray(details?.belongBoards) ? details.belongBoards : [])
    .filter((board) => normalizeBoardName(board?.name).length > 0);
  const boardSignals = buildBoardSignalMaps(details);
  const preparedRelatedBoards = buildPreparedRelatedBoards(relatedBoards, boardSignals);

  const getPriceChangeStyle = (changePct: number | undefined): React.CSSProperties | undefined => {
    if (changePct === undefined || changePct === null) {
      return undefined;
    }

    if (changePct > 0) {
      return { color: 'var(--market-price-up)' };
    }

    if (changePct < 0) {
      return { color: 'var(--market-price-down)' };
    }

    return undefined;
  };

  const formatChangePct = (changePct: number | undefined): string => {
    if (changePct === undefined || changePct === null) return '--';
    const sign = changePct > 0 ? '+' : '';
    return `${sign}${changePct.toFixed(2)}%`;
  };

  const getBoardStatusLabel = (status: BoardStatus): string => {
    if (status === 'leading') {
      return text.leadingBoard;
    }
    return text.laggingBoard;
  };

  const getBoardStatusVariant = (status: BoardStatus): 'success' | 'danger' => {
    if (status === 'leading') {
      return 'success';
    }
    return 'danger';
  };

  const renderBoardChip = (board: PreparedBoard) => (
    <div
      key={board.key}
      className="inline-flex shrink-0 items-center gap-2 text-sm"
    >
      <Badge variant="default" size="sm">
        {board.name}
      </Badge>
      {board.signal && (
        <Badge
          variant={getBoardStatusVariant(board.signal.status)}
          className="shadow-none"
        >
          {getBoardStatusLabel(board.signal.status)}
        </Badge>
      )}
      {board.signal && board.signal.changePct !== undefined && board.signal.changePct !== null && (
        <span
          className="text-xs font-mono"
          style={getPriceChangeStyle(board.signal.changePct)}
        >
          {formatChangePct(board.signal.changePct)}
        </span>
      )}
    </div>
  );

  return (
    <div className="space-y-5">
      {/* 主信息区 - 两列布局 */}
      <div className="grid grid-cols-1 items-stretch gap-5 lg:grid-cols-3">
        {/* 左侧：股票信息与结论 */}
        <div className="lg:col-span-2 space-y-5">
          {/* 股票头部 */}
          <Card variant="gradient" padding="md" className="report-hero">
            <div className="flex items-start justify-between mb-5">
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <h2 className="text-heading-2 font-bold leading-tight text-foreground">
                    {meta.stockName || meta.stockCode}
                  </h2>
                  {/* 价格和涨跌幅 */}
                  {meta.currentPrice != null && (
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-bold font-mono" style={getPriceChangeStyle(meta.changePct)}>
                        {meta.currentPrice.toFixed(2)}
                      </span>
                      <span className="text-sm font-semibold font-mono" style={getPriceChangeStyle(meta.changePct)}>
                        {formatChangePct(meta.changePct)}
                      </span>
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2 mt-1.5">
                  <Badge variant="default" size="sm" className="font-mono">
                    {meta.stockCode}
                  </Badge>
                  {marketPhaseLabel ? (
                    <Badge variant="info" className="shrink-0 gap-1.5 shadow-none" aria-label={marketPhaseLabel}>
                      {marketPhaseLabel}
                    </Badge>
                  ) : null}
                  {partialBarLabel ? (
                    <Badge variant="warning" className="shrink-0 shadow-none" aria-label={partialBarLabel}>
                      {partialBarLabel}
                    </Badge>
                  ) : null}
                  <span className="text-xs text-muted-text flex items-center gap-1">
                    <CalendarDays className="h-3.5 w-3.5" aria-hidden="true" />
                    {formatDateTime(meta.createdAt, language)}
                  </span>
                </div>
              </div>
            </div>

            {/* 关键结论 */}
            <div className="border-t border-border pt-5">
              <span className="label-uppercase">{text.keyInsights}</span>
              <p className="mt-2 max-w-[62ch] whitespace-pre-wrap text-left text-base leading-7 text-foreground">
                {summary.analysisSummary || text.noAnalysisSummary}
              </p>
            </div>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
            {/* 操作建议 */}
            <Card
              variant="bordered"
              padding="sm"
              hoverable
              className="report-insight-card"
              style={{ ['--report-insight-tone' as string]: 'var(--report-strategy-buy)' }}
            >
              <div className="flex items-start gap-3">
                <div className="report-insight-icon flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-success/10">
                  <ClipboardCheck className="h-4 w-4 text-success" aria-hidden="true" />
                </div>
                <div className="space-y-1.5">
                  <h4 className="report-insight-title text-xs font-medium">{text.actionAdvice}</h4>
                  <p
                    className="report-insight-body text-sm font-semibold leading-6"
                    data-testid="report-canonical-action"
                  >
                    {canonicalActionLabel}
                  </p>
                  {supportingAdvice ? (
                    <p className="text-xs leading-5 text-secondary-text">{supportingAdvice}</p>
                  ) : null}
                </div>
              </div>
            </Card>

            {/* 趋势预测 */}
            <Card
              variant="bordered"
              padding="sm"
              hoverable
              className="report-insight-card"
              style={{ ['--report-insight-tone' as string]: 'var(--report-strategy-take)' }}
            >
              <div className="flex items-start gap-3">
                <div className="report-insight-icon flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-warning/10">
                  <TrendingUp className="h-4 w-4 text-warning" aria-hidden="true" />
                </div>
                <div className="space-y-1.5">
                  <h4 className="report-insight-title text-xs font-medium">{text.trendPrediction}</h4>
                  <p className="report-insight-body text-sm leading-6">
                    {summary.trendPrediction || text.noPrediction}
                  </p>
                </div>
              </div>
            </Card>
          </div>

          {preparedRelatedBoards.length > 0 && (
            <Card variant="bordered" padding="sm" className="min-w-0 max-w-full text-left">
              <section aria-label={text.relatedBoards} className="min-w-0 max-w-full">
                <div className="mb-3 flex min-w-0 items-baseline gap-2">
                  <span className="label-uppercase">{text.boardLinkage}</span>
                  <h3 className="mt-0.5 text-base font-semibold text-foreground">{text.relatedBoards}</h3>
                </div>

                <div className="report-related-board-list flex min-h-6 w-full min-w-0 max-w-full flex-nowrap items-center gap-2 overflow-x-auto overscroll-x-contain touch-pan-x pb-1">
                  {preparedRelatedBoards.map(renderBoardChip)}
                </div>
              </section>
            </Card>
          )}
        </div>

        {/* 右侧：情绪指标 / 自选操作 */}
        <div className="flex h-full flex-col space-y-4">
          {watchlist && meta.reportType !== 'market_review' && (
            <Card variant="bordered" padding="sm">
              <div className="text-center space-y-3">
                <span className="label-uppercase">{t('report.watchlist')}</span>
                <div className="text-xs text-muted-text font-mono">{meta.stockCode}</div>
                <Button
                  variant={watchlist.isInWatchlist(meta.stockCode) ? 'danger-subtle' : 'secondary'}
                  size="sm"
                  isLoading={watchlist.isActioning}
                  onClick={() => watchlist.onToggle(meta.stockCode)}
                  className="w-full text-xs"
                >
                  {watchlist.isInWatchlist(meta.stockCode) ? t('report.removeFromWatchlist') : t('report.addToWatchlist')}
                </Button>
                {watchlist.actionMessage && (
                  <p className="text-xs text-secondary-text animate-in fade-in">{watchlist.actionMessage}</p>
                )}
              </div>
            </Card>
          )}
          <Card variant="bordered" padding="md" className="report-rail-card flex-1 !overflow-visible">
            <div className="text-center">
              <h3 className="mb-5 text-sm font-medium text-foreground">{text.marketSentiment}</h3>
              <ScoreGauge score={summary.sentimentScore} size="lg" language={reportLanguage} />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
