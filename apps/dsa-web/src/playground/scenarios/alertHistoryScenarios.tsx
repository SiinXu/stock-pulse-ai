/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useState } from 'react';
import { AlertRuleForm } from '../../components/alerts/AlertRuleForm';
import {
  AlertRuleList,
  type AlertRuleEnabledFilter,
  type AlertTypeFilter,
} from '../../components/alerts/AlertRuleList';
import { AlertTriggerHistory } from '../../components/alerts/AlertTriggerHistory';
import { HistoryList } from '../../components/history/HistoryList';
import { HistoryListItem } from '../../components/history/HistoryListItem';
import { StockBar } from '../../components/history/StockBar';
import { StockBarItemComponent } from '../../components/history/StockBarItem';
import { StockHistoryTrendDrawer } from '../../components/history/StockHistoryTrendDrawer';
import type { StockHistoryRange } from '../../types/analysis';
import {
  fixtureAlertRules,
  fixtureAlertTriggers,
  fixtureHistoryItems,
  fixtureReport,
  fixtureStockBarItems,
} from '../fixtures';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const AlertRuleFormStory = () => {
  const { scenario } = usePlaygroundScenario();
  return <AlertRuleForm isSubmitting={scenario === 'states'} onSubmit={async () => true} />;
};

const AlertRuleListStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [rules, setRules] = useState(fixtureAlertRules);
  const [enabledFilter, setEnabledFilter] = useState<AlertRuleEnabledFilter>('all');
  const [alertTypeFilter, setAlertTypeFilter] = useState<AlertTypeFilter>('all');
  const visibleRules = scenario === 'empty' ? [] : rules;
  return (
    <AlertRuleList
      rules={visibleRules}
      total={visibleRules.length}
      page={1}
      pageSize={20}
      isLoading={scenario === 'loading'}
      enabledFilter={enabledFilter}
      alertTypeFilter={alertTypeFilter}
      onEnabledFilterChange={setEnabledFilter}
      onAlertTypeFilterChange={setAlertTypeFilter}
      onPageChange={() => undefined}
      onToggleEnabled={(rule) => setRules((current) => current.map((item) => item.id === rule.id ? { ...item, enabled: !item.enabled } : item))}
      onDelete={(rule) => setRules((current) => current.filter((item) => item.id !== rule.id))}
      onEdit={() => undefined}
      onTest={() => undefined}
    />
  );
};

const AlertTriggerHistoryStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <AlertTriggerHistory
      triggers={scenario === 'empty' ? [] : fixtureAlertTriggers}
      isLoading={scenario === 'loading'}
      lastUpdated={fixtureAlertTriggers[0]?.triggeredAt}
      onRefresh={() => undefined}
    />
  );
};

const HistoryListStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const items = scenario === 'empty' ? [] : fixtureHistoryItems;
  const toggle = (id: number) => setSelectedIds((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  return (
    <HistoryList
      items={items}
      isLoading={scenario === 'loading'}
      isLoadingMore={false}
      hasMore={false}
      selectedId={items[0]?.id}
      selectedIds={selectedIds}
      onItemClick={() => undefined}
      onLoadMore={() => undefined}
      onToggleItemSelection={toggle}
      onToggleSelectAll={() => setSelectedIds(new Set(items.map((item) => item.id)))}
      onDeleteSelected={() => undefined}
    />
  );
};

const HistoryListItemStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [checked, setChecked] = useState(scenario === 'states');
  return (
    <div className="max-w-sm rounded-lg border border-border bg-card p-2">
      <HistoryListItem
        item={fixtureHistoryItems[0]}
        isViewing={scenario !== 'states'}
        isChecked={checked}
        isDeleting={scenario === 'states'}
        onToggleChecked={() => setChecked((value) => !value)}
        onClick={() => undefined}
      />
    </div>
  );
};

const StockBarStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [items, setItems] = useState(fixtureStockBarItems);
  return (
    <StockBar
      items={scenario === 'empty' ? [] : items}
      isLoading={scenario === 'loading'}
      selectedRecordId={items[0]?.id}
      onItemClick={() => undefined}
      onDeleteStock={(code) => setItems((current) => current.filter((item) => item.stockCode !== code))}
    />
  );
};

const StockBarItemStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <div className="max-w-sm rounded-lg border border-border bg-card p-2">
      <StockBarItemComponent
        item={fixtureStockBarItems[0]}
        isViewing={scenario !== 'states'}
        isDeleting={scenario === 'states'}
        onClick={() => undefined}
        onDelete={() => undefined}
      />
    </div>
  );
};

const StockHistoryTrendDrawerStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [range, setRange] = useState<StockHistoryRange>('all');
  return (
    <StockHistoryTrendDrawer
      report={fixtureReport}
      items={scenario === 'empty' ? [] : fixtureHistoryItems}
      total={scenario === 'empty' ? 0 : fixtureHistoryItems.length}
      hasMore={false}
      isLoading={scenario === 'loading'}
      isLoadingMore={false}
      error={scenario === 'error' ? new Error('playground_fixture_error') : undefined}
      filters={{ range, model: '', sort: 'desc' }}
      onClose={() => undefined}
      onRangeChange={setRange}
      onLoadMore={() => undefined}
      onSelectRecord={() => undefined}
      onRetry={() => undefined}
    />
  );
};

export const ALERT_HISTORY_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'alert-rule-form': AlertRuleFormStory,
  'alert-rule-list': AlertRuleListStory,
  'alert-trigger-history': AlertTriggerHistoryStory,
  'history-list': HistoryListStory,
  'history-list-item': HistoryListItemStory,
  'stock-bar': StockBarStory,
  'stock-bar-item': StockBarItemStory,
  'stock-history-trend-drawer': StockHistoryTrendDrawerStory,
};
