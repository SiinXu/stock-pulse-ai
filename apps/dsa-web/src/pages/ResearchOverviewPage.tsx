// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useEffect, useRef } from 'react';
import {
  Activity,
  ArrowRight,
  BarChart3,
  Calculator,
  CalendarDays,
  FlaskConical,
  Gauge,
  Search,
  type LucideIcon,
} from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { AppPage, Card, PageHeader } from '../components/common';
import { useRouteFocusTarget } from '../components/routing';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { UiLanguage, UiTextKey } from '../i18n/uiText';
import { FINANCIAL_CALCULATORS_TEXT } from '../locales/financialCalculators';
import { APP_ROUTE_PATHS } from '../routing/routes';
import { resolveContextAwareNavigationTarget } from '../utils/sessionContinuity';

type ResearchDestination = {
  key: string;
  titleKey: UiTextKey;
  to: string;
  icon: LucideIcon;
} & (
  | { descriptionKey: UiTextKey }
  | { descriptionSource: 'financialCalculators' }
);

function resolveResearchDestinationDescription(
  destination: ResearchDestination,
  t: (key: UiTextKey) => string,
  language: UiLanguage,
): string {
  if ('descriptionSource' in destination) {
    return FINANCIAL_CALCULATORS_TEXT[language].description;
  }
  return t(destination.descriptionKey);
}

const RESEARCH_DESTINATIONS: readonly ResearchDestination[] = [
  {
    key: 'market',
    titleKey: 'layout.nav.marketReview',
    descriptionKey: 'researchOverview.marketDescription',
    to: APP_ROUTE_PATHS.researchMarket,
    icon: BarChart3,
  },
  {
    key: 'discover',
    titleKey: 'layout.nav.discover',
    descriptionKey: 'researchOverview.discoverDescription',
    to: APP_ROUTE_PATHS.researchDiscover,
    icon: Search,
  },
  {
    key: 'analysis',
    titleKey: 'layout.nav.analysis',
    descriptionKey: 'researchOverview.analysisDescription',
    to: APP_ROUTE_PATHS.researchAnalysis,
    icon: FlaskConical,
  },
  {
    key: 'backtest',
    titleKey: 'layout.nav.backtest',
    descriptionKey: 'researchOverview.backtestDescription',
    to: APP_ROUTE_PATHS.researchBacktest,
    icon: Activity,
  },
  {
    key: 'event-calendar',
    titleKey: 'layout.nav.eventCalendar',
    descriptionKey: 'researchOverview.eventCalendarDescription',
    to: APP_ROUTE_PATHS.eventCalendar,
    icon: CalendarDays,
  },
  {
    key: 'calculators',
    titleKey: 'layout.nav.calculators',
    descriptionSource: 'financialCalculators',
    to: APP_ROUTE_PATHS.calculators,
    icon: Calculator,
  },
  {
    key: 'skill-outcomes',
    titleKey: 'layout.nav.skillOutcomes',
    descriptionKey: 'researchOverview.skillOutcomesDescription',
    to: APP_ROUTE_PATHS.researchSkillOutcomes,
    icon: Gauge,
  },
];

const ResearchOverviewPage: React.FC = () => {
  const { t, language } = useUiLanguage();
  const location = useLocation();
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const currentHref = `${location.pathname}${location.search}${location.hash}`;

  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.research,
    headingRef: pageHeadingRef,
    ready: true,
  });

  useEffect(() => {
    document.title = t('researchOverview.documentTitle');
  }, [t]);

  return (
    <AppPage data-testid="research-overview-page" className="space-y-6">
      <PageHeader
        ref={pageHeadingRef}
        title={t('layout.nav.research')}
        description={t('researchOverview.description')}
      />

      <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-3">
        {RESEARCH_DESTINATIONS.map((destination) => {
          const Icon = destination.icon;
          const title = t(destination.titleKey);
          const description = resolveResearchDestinationDescription(destination, t, language);
          const target = resolveContextAwareNavigationTarget(destination.to, currentHref);

          return (
            <li key={destination.key} className="min-w-0">
              <Card
                level="interactive"
                padding="lg"
                className="flex h-full flex-col"
              >
                <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </div>
                <h2 className="text-lg font-semibold text-foreground">{title}</h2>
                <p className="mt-2 flex-1 text-sm leading-6 text-secondary-text">
                  {description}
                </p>
                <Link
                  to={target}
                  data-control="navigation-link"
                  data-route-focus-key={`research-overview:${destination.key}`}
                  className="control-hit-target mt-5 inline-flex min-h-9 w-fit items-center gap-1.5 rounded-lg text-sm font-medium text-primary underline-offset-4 transition-colors hover:underline focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25 motion-reduce:transition-none"
                >
                  {t('researchOverview.openTool', { tool: title })}
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              </Card>
            </li>
          );
        })}
      </ul>
    </AppPage>
  );
};

export default ResearchOverviewPage;
