// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Lazy workspace-tab surface for the Portfolio route.

import type React from 'react';
import type { UiLanguage } from '../../i18n/uiText';
import { formatUiText } from '../../i18n/uiText';
import type { PortfolioText } from '../../hooks/portfolio/types';
import type { PortfolioEventType } from '../../hooks/portfolio/usePortfolioProjectionSession';
import type {
  PortfolioCashLedgerListItem,
  PortfolioCorporateActionListItem,
  PortfolioTradeListItem,
} from '../../types/portfolio';
import {
  formatCashDirectionLabel,
  formatCorporateActionLabel,
  formatSideLabel,
} from '../../utils/portfolioFormat';
import { Button, Card, EmptyState, SegmentedControl } from '../common';
import type { PortfolioTab } from './portfolioUrlState';

type PortfolioWorkspaceTabsProps = {
  text: PortfolioText;
  language: UiLanguage;
  activeTab: PortfolioTab;
  onTabChange: (tab: PortfolioTab) => void;
  eventType: PortfolioEventType;
  eventLoading: boolean;
  eventPage: number;
  totalEventPages: number;
  tradeEvents: PortfolioTradeListItem[];
  cashEvents: PortfolioCashLedgerListItem[];
  corporateEvents: PortfolioCorporateActionListItem[];
  onOpenLedger: () => void;
  onLedgerPageChange: (page: number) => void;
};

const PortfolioWorkspaceTabs: React.FC<PortfolioWorkspaceTabsProps> = ({
  text,
  language,
  activeTab,
  onTabChange,
  eventType,
  eventLoading,
  eventPage,
  totalEventPages,
  tradeEvents,
  cashEvents,
  corporateEvents,
  onOpenLedger,
  onLedgerPageChange,
}) => (
  <>
    <SegmentedControl
      id="portfolio-workspace-tabs"
      ariaLabel={text.workspaceTabsLabel}
      value={activeTab}
      onChange={onTabChange}
      options={[
        { value: 'positions', label: text.positionsTitle },
        { value: 'ledger', label: text.eventLog },
        { value: 'risk', label: text.tabRisk },
      ]}
    />

    {activeTab === 'ledger' ? (
      <Card padding="md" data-testid="portfolio-tab-ledger" className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-foreground">{text.eventLog}</h2>
          <Button
            type="button"
            variant="secondary"
            size="comfortable"
            onClick={onOpenLedger}
          >
            {text.refreshLedger}
          </Button>
        </div>
        <p className="text-xs text-secondary-text">{text.deleteHint}</p>
        <div className="max-h-96 overflow-auto rounded-lg border border-subtle p-2">
          {eventType === 'trade' && tradeEvents.map((item) => (
            <div key={`tab-t-${item.id}`} className="border-b border-subtle py-2 text-xs text-secondary">
              {formatUiText(text.tradeRow, {
                date: item.tradeDate,
                side: formatSideLabel(item.side, language),
                symbol: item.symbol,
                quantity: item.quantity,
                price: item.price,
              })}
            </div>
          ))}
          {eventType === 'cash' && cashEvents.map((item) => (
            <div key={`tab-c-${item.id}`} className="border-b border-subtle py-2 text-xs text-secondary">
              {item.eventDate} {formatCashDirectionLabel(item.direction, language)} {item.amount} {item.currency}
            </div>
          ))}
          {eventType === 'corporate' && corporateEvents.map((item) => (
            <div key={`tab-ca-${item.id}`} className="border-b border-subtle py-2 text-xs text-secondary">
              {item.effectiveDate} {formatCorporateActionLabel(item.actionType, language)} {item.symbol}
            </div>
          ))}
          {!eventLoading
            && ((eventType === 'trade' && tradeEvents.length === 0)
              || (eventType === 'cash' && cashEvents.length === 0)
              || (eventType === 'corporate' && corporateEvents.length === 0)) ? (
                <EmptyState title={text.noLedger} description={text.noLedgerDescription} compact />
              ) : null}
        </div>
        <div className="flex items-center justify-between text-xs text-secondary">
          <span>{formatUiText(text.page, { page: eventPage, pages: totalEventPages })}</span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              size="comfortable"
              className="text-xs"
              disabled={eventPage <= 1}
              onClick={() => onLedgerPageChange(Math.max(1, eventPage - 1))}
            >
              {text.prevPage}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="comfortable"
              className="text-xs"
              disabled={eventPage >= totalEventPages}
              onClick={() => onLedgerPageChange(Math.min(totalEventPages, eventPage + 1))}
            >
              {text.nextPage}
            </Button>
          </div>
        </div>
      </Card>
    ) : null}
  </>
);

export default PortfolioWorkspaceTabs;
