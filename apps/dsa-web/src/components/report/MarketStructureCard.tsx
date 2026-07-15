import type React from 'react';
import { AlertTriangle, Map, TrendingUp } from 'lucide-react';
import type {
  MarketStructureContext,
  MarketStructureStatus,
  MarketStructureThemePhase,
  MarketStructureStockRole,
  RankedThemeItem,
  ReportLanguage,
} from '../../types/analysis';
import {
  MARKET_STRUCTURE_RISK_TAG_TEXT as RISK_TAG_TEXT,
  MARKET_STRUCTURE_TEXT as TEXT,
} from '../../locales/reportBody';
import { normalizeReportLanguage } from '../../utils/reportLanguage';
import { Badge, Card } from '../common';
import { DashboardPanelHeader } from '../dashboard';

interface MarketStructureCardProps {
  context?: MarketStructureContext | null;
  language?: ReportLanguage;
}

type BadgeVariant = NonNullable<React.ComponentProps<typeof Badge>['variant']>;

const STATUS_VARIANT: Record<MarketStructureStatus, BadgeVariant> = {
  ok: 'success',
  partial: 'warning',
  unknown: 'default',
  not_supported: 'default',
};

const formatItem = (item: RankedThemeItem): string => {
  if (typeof item.changePct === 'number') {
    return `${item.name} ${item.changePct > 0 ? '+' : ''}${item.changePct.toFixed(2)}%`;
  }
  return item.name;
};

const itemList = (items?: RankedThemeItem[], limit = 4): string[] => {
  if (!Array.isArray(items)) {
    return [];
  }
  return items.filter((item) => item?.name).slice(0, limit).map(formatItem);
};

const valueList = (items?: string[], limit = 4): string[] => {
  if (!Array.isArray(items)) {
    return [];
  }
  return items.filter(Boolean).slice(0, limit);
};

export const MarketStructureCard: React.FC<MarketStructureCardProps> = ({ context, language }) => {
  if (!context || context.schemaVersion !== 'market-structure-v1' || context.status === 'not_supported') {
    return null;
  }

  const reportLanguage = normalizeReportLanguage(language);
  const text = reportLanguage === 'en'
    ? TEXT.en
    : reportLanguage === 'ko'
      ? TEXT.ko
      : TEXT.zh;
  const marketTheme = context.marketThemeContext;
  const stockPosition = context.stockMarketPosition;
  if (!marketTheme || !stockPosition) {
    return null;
  }

  const activeThemes = itemList(marketTheme.activeThemes);
  const leadingConcepts = itemList(marketTheme.leadingConcepts);
  const leadingIndustries = itemList(marketTheme.leadingIndustries);
  const primaryTheme = stockPosition.primaryTheme?.name || text.empty;
  const themePhase = (stockPosition.themePhase || 'unknown') as MarketStructureThemePhase;
  const stockRole = (stockPosition.stockRole || 'unknown') as MarketStructureStockRole;
  const themePhaseLabel = text.phase[themePhase] || stockPosition.themePhase || text.phase.unknown;
  const stockRoleLabel = text.role[stockRole] || stockPosition.stockRole || text.role.unknown;
  const riskTags = valueList(
    stockPosition.riskTags?.map(
      (tag) =>
        (RISK_TAG_TEXT[reportLanguage] as Record<string, string>)[tag.code]
        || tag.message
        || tag.code,
    ),
  );
  const missingFields = valueList([
    ...(stockPosition.missingFields || []),
    ...(marketTheme.dataQuality?.missingFields || []),
  ]);

  const hasContent = [
    activeThemes,
    leadingConcepts,
    leadingIndustries,
    riskTags,
    missingFields,
  ].some((items) => items.length > 0) || primaryTheme !== text.empty;
  if (!hasContent) {
    return null;
  }

  return (
    <Card padding="md">
      <section aria-label={text.title}>
        <DashboardPanelHeader
          leading={<Map className="h-4 w-4 text-success" aria-hidden="true" />}
          eyebrow={text.eyebrow}
          title={text.title}
          actions={
            <Badge variant={STATUS_VARIANT[context.status] || 'default'}>
              {text.status[context.status] || context.status}
            </Badge>
          }
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <TrendingUp className="h-4 w-4 text-success" aria-hidden="true" />
              <span>{text.marketLayer}</span>
              <Badge variant={STATUS_VARIANT[marketTheme.status] || 'default'}>
                {text.status[marketTheme.status] || marketTheme.status}
              </Badge>
            </div>
            <MetricLine label={text.activeThemes} values={activeThemes} emptyText={text.empty} />
            <MetricLine label={text.leadingConcepts} values={leadingConcepts} emptyText={text.empty} />
            <MetricLine label={text.leadingIndustries} values={leadingIndustries} emptyText={text.empty} />
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Map className="h-4 w-4 text-success" aria-hidden="true" />
              <span>{text.stockLayer}</span>
              <Badge variant={STATUS_VARIANT[stockPosition.status] || 'default'}>
                {text.status[stockPosition.status] || stockPosition.status}
              </Badge>
            </div>
            <MetricLine label={text.primaryTheme} values={[primaryTheme]} emptyText={text.empty} />
            <MetricLine
              label={text.themePhase}
              values={[themePhaseLabel]}
              emptyText={text.empty}
            />
            <MetricLine
              label={text.stockRole}
              values={[stockRoleLabel]}
              emptyText={text.empty}
            />
          </div>
        </div>

        {(riskTags.length > 0 || missingFields.length > 0) && (
          <div className="mt-4 grid gap-3 border-t border-border/60 pt-4 md:grid-cols-2">
            {riskTags.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-secondary-text">
                  <AlertTriangle className="h-3.5 w-3.5 text-warning" aria-hidden="true" />
                  <span>{text.riskTags}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {riskTags.map((item) => (
                    <Badge key={item} variant="warning">{item}</Badge>
                  ))}
                </div>
              </div>
            )}
            {missingFields.length > 0 && (
              <div>
                <div className="mb-2 text-xs font-medium uppercase tracking-wide text-secondary-text">
                  {text.missingFields}
                </div>
                <div className="flex flex-wrap gap-2">
                  {missingFields.map((item) => (
                    <Badge key={item} variant="default">{item}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </Card>
  );
};

interface MetricLineProps {
  label: string;
  values: string[];
  emptyText: string;
}

const MetricLine: React.FC<MetricLineProps> = ({ label, values, emptyText }) => (
  <div className="grid gap-1 text-sm sm:grid-cols-[7rem_1fr]">
    <span className="text-secondary-text">{label}</span>
    <span className="min-w-0 break-words text-foreground">
      {values.length > 0 ? values.join(' / ') : emptyText}
    </span>
  </div>
);
