import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pie, PieChart, ResponsiveContainer, Tooltip, Legend, Cell } from 'recharts';
import { X } from 'lucide-react';
import { decisionSignalsApi } from '../api/decisionSignals';
import { portfolioApi } from '../api/portfolio';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, Badge, Button, Card, Checkbox, ConfirmDialog, DatePicker, EmptyState, IconButton, InlineAlert, Input, Modal, Select } from '../components/common';
import { PortfolioSignalSummary } from '../components/decision-signals/DecisionSignalDisplay';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { getUiClauseSeparator } from '../utils/uiLocale';
import { formatUiText, type UiLanguage } from '../i18n/uiText';
import { PORTFOLIO_FILE_TEXT, PORTFOLIO_LIMITATION_LABELS, PORTFOLIO_TEXT } from '../locales/portfolio';
import type { FxRefreshFeedback } from '../utils/portfolioFormat';
import {
  buildFxRefreshFeedback,
  formatBrokerLabel,
  formatCashDirectionLabel,
  formatCorporateActionLabel,
  formatMoney,
  formatPct,
  formatPositionMoney,
  formatPositionPrice,
  formatSideLabel,
  formatSignedPct,
  getCsvCommitVariant,
  getCsvParseVariant,
  getFxRefreshFeedbackVariant,
  getPositionPriceLabel,
  getTodayIso,
  hasPositionPrice,
} from '../utils/portfolioFormat';
import type {
  DecisionSignalItem,
  DecisionSignalMarket,
} from '../types/decisionSignals';
import type {
  PortfolioAccountItem,
  PortfolioCashDirection,
  PortfolioCashLedgerListItem,
  PortfolioCorporateActionListItem,
  PortfolioCorporateActionType,
  PortfolioCostMethod,
  PortfolioImportBrokerItem,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioPositionItem,
  PortfolioRiskResponse,
  PortfolioSide,
  PortfolioSnapshotResponse,
  PortfolioTradeListItem,
} from '../types/portfolio';
import { areStockCodesEquivalent, normalizeStockCode } from '../utils/stockCode';
import { parseDecisionSignalDate } from '../utils/decisionSignalTime';
import { buildDecisionActionLabelMap, getDecisionActionLabel } from '../utils/decisionAction';
import { createOperationId } from '../utils/operationId';

const PIE_COLORS = [
  'hsl(var(--primary))',
  'hsl(var(--secondary-text))',
  'hsl(var(--warning))',
  'hsl(var(--destructive))',
  'hsl(var(--muted-text))',
  'hsl(var(--foreground) / 0.65)',
];
const DEFAULT_PAGE_SIZE = 20;
const PORTFOLIO_SIGNAL_LOOKUP_CONCURRENCY = 6;

type AccountOption = 'all' | number;
type EventType = 'trade' | 'cash' | 'corporate';

type FlatPosition = PortfolioPositionItem & {
  accountId: number;
  accountName: string;
};

type PortfolioSignalLookup = {
  stockCode: string;
  market?: DecisionSignalMarket;
};

type PortfolioSignalLookupResult = {
  items: DecisionSignalItem[];
  error: string | null;
};

type PendingDelete =
  | { eventType: 'trade'; id: number; message: string }
  | { eventType: 'cash'; id: number; message: string }
  | { eventType: 'corporate'; id: number; message: string };

type PendingAccountDelete = {
  accountId: number;
  accountName: string;
};

type FxRefreshContext = {
  viewKey: string;
  requestId: number;
};

type OperationAttempt = {
  fingerprint: string;
  operationId: string;
};

function resolveOperationAttempt(
  current: OperationAttempt | null,
  fingerprint: string,
  scope: string,
): OperationAttempt {
  if (current?.fingerprint === fingerprint) {
    return current;
  }
  return { fingerprint, operationId: createOperationId(scope) };
}

const PORTFOLIO_DATE_TRIGGER_CLASS =
  'h-11 w-full rounded-sm border border-border bg-transparent px-3 text-xs text-foreground placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text disabled:cursor-not-allowed disabled:opacity-60';
const PORTFOLIO_FILE_PICKER_CLASS =
  'flex h-11 w-full cursor-pointer items-center justify-center rounded-full border border-border bg-transparent px-3 text-xs text-foreground transition-colors duration-200 hover:bg-hover focus:outline-none focus:border-muted-text disabled:cursor-not-allowed disabled:opacity-60';

function getSignalTime(item: DecisionSignalItem): number {
  return parseDecisionSignalDate(item.createdAt)?.getTime()
    ?? parseDecisionSignalDate(item.updatedAt)?.getTime()
    ?? 0;
}

function isNewerSignal(left: DecisionSignalItem | undefined, right: DecisionSignalItem): boolean {
  if (!left) return true;
  return getSignalTime(right) > getSignalTime(left);
}

function formatPortfolioLimitation(limitation: string, language: UiLanguage): string {
  return PORTFOLIO_LIMITATION_LABELS[language][limitation] ?? limitation;
}

const DECISION_SIGNAL_MARKETS = new Set<DecisionSignalMarket>(['cn', 'hk', 'us', 'jp', 'kr', 'tw']);
type PortfolioAccountMarket = 'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw';

function toDecisionSignalMarket(value: string | null | undefined): DecisionSignalMarket | undefined {
  const normalized = String(value || '').toLowerCase();
  return DECISION_SIGNAL_MARKETS.has(normalized as DecisionSignalMarket)
    ? normalized as DecisionSignalMarket
    : undefined;
}

function toPositionSignalLookupKey(stockCode: string, market?: DecisionSignalMarket): string {
  return `${market || ''}:${normalizeStockCode(stockCode).toUpperCase()}`;
}

async function mapWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  mapper: (item: T) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let nextIndex = 0;
  const workerCount = Math.min(Math.max(1, concurrency), items.length);

  await Promise.all(Array.from({ length: workerCount }, async () => {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;
      results[currentIndex] = await mapper(items[currentIndex]);
    }
  }));

  return results;
}

async function loadPortfolioSignalLookup(lookup: PortfolioSignalLookup): Promise<PortfolioSignalLookupResult> {
  try {
    const response = await decisionSignalsApi.getLatest(lookup.stockCode, {
      market: lookup.market,
      limit: 1,
    });
    return { items: response.items, error: null };
  } catch (err) {
    return { items: [], error: getParsedApiError(err).message };
  }
}

const PortfolioPage: React.FC = () => {
  const { language, t } = useUiLanguage();
  const text = PORTFOLIO_TEXT[language];
  const fileText = PORTFOLIO_FILE_TEXT[language];
  const decisionActionLabels = useMemo(() => buildDecisionActionLabelMap(t), [t]);

  // Set page title
  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<AccountOption>('all');
  const [showCreateAccount, setShowCreateAccount] = useState(false);
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [cashModalOpen, setCashModalOpen] = useState(false);
  const [corpModalOpen, setCorpModalOpen] = useState(false);
  const [tradeSubmitting, setTradeSubmitting] = useState(false);
  const [tradeError, setTradeError] = useState<ParsedApiError | null>(null);
  const [cashSubmitting, setCashSubmitting] = useState(false);
  const [cashError, setCashError] = useState<ParsedApiError | null>(null);
  const [corpSubmitting, setCorpSubmitting] = useState(false);
  const [corpError, setCorpError] = useState<ParsedApiError | null>(null);
  const [csvModalOpen, setCsvModalOpen] = useState(false);
  const [eventModalOpen, setEventModalOpen] = useState(false);
  const [accountCreating, setAccountCreating] = useState(false);
  const [accountCreateError, setAccountCreateError] = useState<string | null>(null);
  const [accountCreateSuccess, setAccountCreateSuccess] = useState<string | null>(null);
  const [accountForm, setAccountForm] = useState({
    name: '',
    broker: 'Demo',
    market: 'cn' as PortfolioAccountMarket,
    baseCurrency: 'CNY',
  });
  const [costMethod, setCostMethod] = useState<PortfolioCostMethod>('fifo');
  const [snapshot, setSnapshot] = useState<PortfolioSnapshotResponse | null>(null);
  const [risk, setRisk] = useState<PortfolioRiskResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [fxRefreshing, setFxRefreshing] = useState(false);
  const [fxRefreshFeedback, setFxRefreshFeedback] = useState<FxRefreshFeedback | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [riskWarning, setRiskWarning] = useState<string | null>(null);
  const [writeWarning, setWriteWarning] = useState<string | null>(null);
  const [portfolioSignals, setPortfolioSignals] = useState<DecisionSignalItem[]>([]);
  const [portfolioSignalsLoading, setPortfolioSignalsLoading] = useState(false);
  const [portfolioSignalsWarning, setPortfolioSignalsWarning] = useState<string | null>(null);
  const [portfolioSignalsRefreshKey, setPortfolioSignalsRefreshKey] = useState(0);
  const portfolioSignalsRequestRef = useRef(0);
  const [positionAnalysisLoadingKey, setPositionAnalysisLoadingKey] = useState<string | null>(null);
  const [positionAnalysisMessage, setPositionAnalysisMessage] = useState<string | null>(null);

  const [brokers, setBrokers] = useState<PortfolioImportBrokerItem[]>([]);
  const [selectedBroker, setSelectedBroker] = useState('');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvDryRun, setCsvDryRun] = useState(true);
  const [csvParsing, setCsvParsing] = useState(false);
  const [csvCommitting, setCsvCommitting] = useState(false);
  const [csvError, setCsvError] = useState<ParsedApiError | null>(null);
  const [csvParseResult, setCsvParseResult] = useState<PortfolioImportParseResponse | null>(null);
  const [csvCommitResult, setCsvCommitResult] = useState<PortfolioImportCommitResponse | null>(null);
  const [brokerLoadWarning, setBrokerLoadWarning] = useState<string | null>(null);

  const [eventType, setEventType] = useState<EventType>('trade');
  const [eventDateFrom, setEventDateFrom] = useState('');
  const [eventDateTo, setEventDateTo] = useState('');
  const [eventSymbol, setEventSymbol] = useState('');
  const [eventSide, setEventSide] = useState<'' | PortfolioSide>('');
  const [eventDirection, setEventDirection] = useState<'' | PortfolioCashDirection>('');
  const [eventActionType, setEventActionType] = useState<'' | PortfolioCorporateActionType>('');
  const [appliedEventFilters, setAppliedEventFilters] = useState({
    dateFrom: '',
    dateTo: '',
    symbol: '',
    side: '' as '' | PortfolioSide,
    direction: '' as '' | PortfolioCashDirection,
    actionType: '' as '' | PortfolioCorporateActionType,
  });
  const [eventPage, setEventPage] = useState(1);
  const [eventRefreshKey, setEventRefreshKey] = useState(0);
  const [eventTotal, setEventTotal] = useState(0);
  const [eventLoading, setEventLoading] = useState(false);
  const [eventError, setEventError] = useState<ParsedApiError | null>(null);
  const [tradeEvents, setTradeEvents] = useState<PortfolioTradeListItem[]>([]);
  const [cashEvents, setCashEvents] = useState<PortfolioCashLedgerListItem[]>([]);
  const [corporateEvents, setCorporateEvents] = useState<PortfolioCorporateActionListItem[]>([]);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [pendingAccountDelete, setPendingAccountDelete] = useState<PendingAccountDelete | null>(null);
  const [accountDeleteLoading, setAccountDeleteLoading] = useState(false);
  const [accountDeleteError, setAccountDeleteError] = useState<string | null>(null);

  const [tradeForm, setTradeForm] = useState({
    symbol: '',
    tradeDate: getTodayIso(),
    side: 'buy' as PortfolioSide,
    quantity: '',
    price: '',
    fee: '',
    tax: '',
    tradeUid: '',
    note: '',
  });
  const [cashForm, setCashForm] = useState({
    eventDate: getTodayIso(),
    direction: 'in' as PortfolioCashDirection,
    amount: '',
    currency: '',
    note: '',
  });
  const [corpForm, setCorpForm] = useState({
    symbol: '',
    effectiveDate: getTodayIso(),
    actionType: 'cash_dividend' as PortfolioCorporateActionType,
    cashDividendPerShare: '',
    splitRatio: '',
    note: '',
  });
  const tradeOperationRef = useRef<OperationAttempt | null>(null);
  const cashOperationRef = useRef<OperationAttempt | null>(null);
  const corporateOperationRef = useRef<OperationAttempt | null>(null);
  const csvOperationRef = useRef<OperationAttempt | null>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);
  const snapshotRequestRef = useRef(0);
  const eventRequestRef = useRef(0);

  const queryAccountId = selectedAccount === 'all' ? undefined : selectedAccount;
  const refreshViewKey = `${selectedAccount === 'all' ? 'all' : `account:${selectedAccount}`}:cost:${costMethod}`;
  const refreshContextRef = useRef<FxRefreshContext>({ viewKey: refreshViewKey, requestId: 0 });
  const hasAccounts = accounts.length > 0;
  const writableAccount = selectedAccount === 'all' ? undefined : accounts.find((item) => item.id === selectedAccount);
  const writableAccountId = writableAccount?.id;
  const writeBlocked = !writableAccountId;
  const canDeleteSelectedAccount = Boolean(writableAccountId) && !isLoading && !fxRefreshing && !accountDeleteLoading;
  const totalEventPages = Math.max(1, Math.ceil(eventTotal / DEFAULT_PAGE_SIZE));
  const currentEventCount = eventType === 'trade'
    ? tradeEvents.length
    : eventType === 'cash'
      ? cashEvents.length
      : corporateEvents.length;

  const isActiveRefreshContext = (requestedViewKey: string, requestedRequestId: number) => {
    return (
      refreshContextRef.current.viewKey === requestedViewKey
      && refreshContextRef.current.requestId === requestedRequestId
    );
  };

  const loadAccounts = useCallback(async () => {
    try {
      const response = await portfolioApi.getAccounts(false);
      const items = response.accounts || [];
      setAccounts(items);
      setSelectedAccount((prev) => {
        if (items.length === 0) return 'all';
        if (prev !== 'all' && !items.some((item) => item.id === prev)) return items[0].id;
        return prev;
      });
    } catch (err) {
      setError(getParsedApiError(err));
    }
  }, []);

  const loadBrokers = useCallback(async () => {
    try {
      const response = await portfolioApi.listImportBrokers();
      const brokerItems = response.brokers || [];
      if (brokerItems.length === 0) {
        setBrokers([]);
        setBrokerLoadWarning(text.brokerListEmpty);
        setSelectedBroker('');
        return;
      }
      setBrokers(brokerItems);
      setBrokerLoadWarning(null);
      setSelectedBroker((current) => (
        brokerItems.some((item) => item.broker === current) ? current : brokerItems[0].broker
      ));
    } catch {
      setBrokers([]);
      setBrokerLoadWarning(text.brokerListUnavailable);
      setSelectedBroker('');
    }
  }, [text.brokerListEmpty, text.brokerListUnavailable]);

  const loadSnapshotAndRisk = useCallback(async () => {
    const requestId = snapshotRequestRef.current + 1;
    snapshotRequestRef.current = requestId;
    setIsLoading(true);
    setRiskWarning(null);
    try {
      const snapshotData = await portfolioApi.getSnapshot({
        accountId: queryAccountId,
        costMethod,
        includeRealtime: false,
      });
      if (requestId !== snapshotRequestRef.current) return;
      setSnapshot(snapshotData);
      setError(null);

      try {
        const riskData = await portfolioApi.getRisk({
          accountId: queryAccountId,
          costMethod,
          includeRealtime: false,
        });
        if (requestId === snapshotRequestRef.current) {
          setRisk(riskData);
        }
      } catch (riskErr) {
        if (requestId !== snapshotRequestRef.current) return;
        setRisk(null);
        setRiskWarning(getParsedApiError(riskErr, language).message || text.riskFallback);
      }
    } catch (err) {
      if (requestId !== snapshotRequestRef.current) return;
      setSnapshot(null);
      setRisk(null);
      setError(getParsedApiError(err));
    } finally {
      if (requestId === snapshotRequestRef.current) {
        setIsLoading(false);
      }
    }
  }, [queryAccountId, costMethod, language, text.riskFallback]);

  const loadEventsPage = useCallback(async (page: number) => {
    const requestId = eventRequestRef.current + 1;
    eventRequestRef.current = requestId;
    setEventLoading(true);
    setEventError(null);
    try {
      if (eventType === 'trade') {
        const response = await portfolioApi.listTrades({
          accountId: queryAccountId,
          dateFrom: appliedEventFilters.dateFrom || undefined,
          dateTo: appliedEventFilters.dateTo || undefined,
          symbol: appliedEventFilters.symbol || undefined,
          side: appliedEventFilters.side || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        if (requestId !== eventRequestRef.current) return;
        setTradeEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else if (eventType === 'cash') {
        const response = await portfolioApi.listCashLedger({
          accountId: queryAccountId,
          dateFrom: appliedEventFilters.dateFrom || undefined,
          dateTo: appliedEventFilters.dateTo || undefined,
          direction: appliedEventFilters.direction || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        if (requestId !== eventRequestRef.current) return;
        setCashEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else {
        const response = await portfolioApi.listCorporateActions({
          accountId: queryAccountId,
          dateFrom: appliedEventFilters.dateFrom || undefined,
          dateTo: appliedEventFilters.dateTo || undefined,
          symbol: appliedEventFilters.symbol || undefined,
          actionType: appliedEventFilters.actionType || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        if (requestId !== eventRequestRef.current) return;
        setCorporateEvents(response.items || []);
        setEventTotal(response.total || 0);
      }
    } catch (err) {
      if (requestId === eventRequestRef.current) {
        setEventError(getParsedApiError(err));
      }
    } finally {
      if (requestId === eventRequestRef.current) {
        setEventLoading(false);
      }
    }
  }, [
    appliedEventFilters,
    eventType,
    queryAccountId,
  ]);

  const loadEvents = useCallback(async () => {
    await loadEventsPage(eventPage);
  }, [eventPage, loadEventsPage]);

  const applyEventFilters = useCallback(() => {
    setEventPage(1);
    setAppliedEventFilters({
      dateFrom: eventDateFrom,
      dateTo: eventDateTo,
      symbol: eventSymbol.trim(),
      side: eventSide,
      direction: eventDirection,
      actionType: eventActionType,
    });
    setEventRefreshKey((current) => current + 1);
  }, [eventActionType, eventDateFrom, eventDateTo, eventDirection, eventSide, eventSymbol]);

  const refreshPortfolioData = useCallback(async (page = eventPage) => {
    await Promise.all([loadSnapshotAndRisk(), loadEventsPage(page)]);
  }, [eventPage, loadEventsPage, loadSnapshotAndRisk]);

  useEffect(() => {
    void loadAccounts();
    void loadBrokers();
  }, [loadAccounts, loadBrokers]);

  useEffect(() => {
    void loadSnapshotAndRisk();
  }, [loadSnapshotAndRisk]);

  useEffect(() => {
    void loadEvents();
  }, [eventRefreshKey, loadEvents]);

  useEffect(() => {
    refreshContextRef.current = {
      viewKey: refreshViewKey,
      requestId: refreshContextRef.current.requestId + 1,
    };
    setFxRefreshing(false);
    setFxRefreshFeedback(null);
  }, [refreshViewKey]);

  useEffect(() => {
    setEventPage(1);
  }, [eventType, queryAccountId]);

  useEffect(() => {
    if (!writeBlocked) {
      setWriteWarning(null);
    }
  }, [writeBlocked]);

  const positionRows: FlatPosition[] = useMemo(() => {
    if (!snapshot) return [];
    const rows: FlatPosition[] = [];
    for (const account of snapshot.accounts || []) {
      for (const position of account.positions || []) {
        rows.push({
          ...position,
          accountId: account.accountId,
          accountName: account.accountName,
        });
      }
    }
    rows.sort((a, b) => Number(b.marketValueBase || 0) - Number(a.marketValueBase || 0));
    return rows;
  }, [snapshot]);

  const snapshotMatchesAccountScope = useMemo(() => {
    if (!snapshot) return false;
    const snapshotAccountIds = new Set((snapshot.accounts || []).map((account) => account.accountId));
    if (queryAccountId !== undefined) {
      return snapshotAccountIds.size === 1 && snapshotAccountIds.has(queryAccountId);
    }
    return accounts.length === 0 || Number(snapshot.accountCount || 0) === accounts.length;
  }, [accounts.length, queryAccountId, snapshot]);

  const positionSignalLookups = useMemo(() => {
    const lookups = new Map<string, PortfolioSignalLookup>();
    for (const row of positionRows) {
      const stockCode = String(row.symbol || '').trim();
      if (!stockCode) continue;
      const market = toDecisionSignalMarket(row.market);
      const key = toPositionSignalLookupKey(stockCode, market);
      if (!lookups.has(key)) {
        lookups.set(key, { stockCode, market });
      }
    }
    return Array.from(lookups.values());
  }, [positionRows]);

  useEffect(() => {
    const requestId = portfolioSignalsRequestRef.current + 1;
    portfolioSignalsRequestRef.current = requestId;

    if (positionSignalLookups.length === 0 || !snapshotMatchesAccountScope) {
      setPortfolioSignals([]);
      setPortfolioSignalsWarning(null);
      setPortfolioSignalsLoading(false);
      return;
    }

    const isActiveRequest = () => portfolioSignalsRequestRef.current === requestId;

    const loadPortfolioSignals = async () => {
      setPortfolioSignalsLoading(true);
      setPortfolioSignalsWarning(null);
      const results = await mapWithConcurrency(
        positionSignalLookups,
        PORTFOLIO_SIGNAL_LOOKUP_CONCURRENCY,
        loadPortfolioSignalLookup,
      );
      if (!isActiveRequest()) return;
      const collected = results.flatMap((result) => result.items);
      const failures = results.flatMap((result) => (result.error ? [result.error] : []));
      setPortfolioSignals(collected);
      setPortfolioSignalsWarning(
        failures.length > 0
          ? (
              collected.length > 0
                ? formatUiText(t('decisionSignals.portfolioPartialWarning'), { message: failures[0] })
                : failures[0]
            )
          : null,
      );
      if (isActiveRequest()) {
        setPortfolioSignalsLoading(false);
      }
    };

    void loadPortfolioSignals();

    return () => {
      portfolioSignalsRequestRef.current += 1;
    };
  }, [portfolioSignalsRefreshKey, positionSignalLookups, snapshotMatchesAccountScope, t]);

  const signalByPositionKey = useMemo(() => {
    const mapped = new Map<string, DecisionSignalItem>();
    for (const row of positionRows) {
      const rowMarket = String(row.market || '').toLowerCase();
      for (const signal of portfolioSignals) {
        const signalMarket = String(signal.market || '').toLowerCase();
        if (rowMarket && signalMarket && rowMarket !== signalMarket) {
          continue;
        }
        if (!areStockCodesEquivalent(row.symbol, signal.stockCode)) {
          continue;
        }
        const key = `${row.accountId}-${row.symbol}-${row.market}`;
        const existing = mapped.get(key);
        if (isNewerSignal(existing, signal)) {
          mapped.set(key, signal);
        }
      }
    }
    return mapped;
  }, [portfolioSignals, positionRows]);

  const handleAnalyzePosition = async (row: FlatPosition) => {
    const key = `${row.accountId}-${row.symbol}-${row.market}`;
    setPositionAnalysisLoadingKey(key);
    setPositionAnalysisMessage(null);
    setError(null);
    try {
      const task = await portfolioApi.analyzePosition(row.symbol, {
        accountId: row.accountId,
        analysisPhase: 'auto',
        force: false,
      });
      setPositionAnalysisMessage(formatUiText(text.analysisSubmitted, { symbol: row.symbol, taskId: task.taskId }));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setPositionAnalysisLoadingKey(null);
    }
  };

  const sectorPieData = useMemo(() => {
    const sectors = risk?.sectorConcentration?.topSectors || [];
    return sectors
      .slice(0, 6)
      .map((item) => ({
        name: item.sector,
        value: Number(item.weightPct || 0),
      }))
      .filter((item) => item.value > 0);
  }, [risk]);

  const positionFallbackPieData = useMemo(() => {
    if (!risk?.concentration?.topPositions?.length) {
      return [];
    }
    return risk.concentration.topPositions
      .slice(0, 6)
      .map((item) => ({
        name: item.symbol,
        value: Number(item.weightPct || 0),
      }))
      .filter((item) => item.value > 0);
  }, [risk]);

  const concentrationPieData = sectorPieData.length > 0 ? sectorPieData : positionFallbackPieData;
  const concentrationMode = sectorPieData.length > 0 ? 'sector' : 'position';

  const handleTradeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) {
      setWriteWarning(text.selectAccountWrite);
      return;
    }
    if (!Number.isFinite(Number(tradeForm.quantity)) || Number(tradeForm.quantity) <= 0) {
      document.getElementById('portfolio-trade-quantity')?.focus();
      return;
    }
    if (!Number.isFinite(Number(tradeForm.price)) || Number(tradeForm.price) <= 0) {
      document.getElementById('portfolio-trade-price')?.focus();
      return;
    }
    if (tradeSubmitting) return;
    const requestPayload = {
      accountId: writableAccountId,
      symbol: tradeForm.symbol,
      tradeDate: tradeForm.tradeDate,
      side: tradeForm.side,
      quantity: Number(tradeForm.quantity),
      price: Number(tradeForm.price),
      fee: Number(tradeForm.fee || 0),
      tax: Number(tradeForm.tax || 0),
      tradeUid: tradeForm.tradeUid || undefined,
      note: tradeForm.note || undefined,
    };
    const attempt = resolveOperationAttempt(
      tradeOperationRef.current,
      JSON.stringify(requestPayload),
      'portfolio-trade',
    );
    tradeOperationRef.current = attempt;
    setTradeSubmitting(true);
    setTradeError(null);
    setWriteWarning(null);
    try {
      await portfolioApi.createTrade({
        ...requestPayload,
        operationId: attempt.operationId,
      });
    } catch (err) {
      setTradeError(getParsedApiError(err));
      setTradeSubmitting(false);
      return;
    }
    tradeOperationRef.current = null;
    setTradeForm((prev) => ({ ...prev, symbol: '', tradeUid: '', note: '' }));
    setTradeModalOpen(false);
    setTradeSubmitting(false);
    await refreshPortfolioData();
  };

  const handleCashSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) {
      setWriteWarning(text.selectAccountWrite);
      return;
    }
    if (!Number.isFinite(Number(cashForm.amount)) || Number(cashForm.amount) <= 0) {
      document.getElementById('portfolio-cash-amount')?.focus();
      return;
    }
    if (cashSubmitting) return;
    const requestPayload = {
      accountId: writableAccountId,
      eventDate: cashForm.eventDate,
      direction: cashForm.direction,
      amount: Number(cashForm.amount),
      currency: cashForm.currency || undefined,
      note: cashForm.note || undefined,
    };
    const attempt = resolveOperationAttempt(
      cashOperationRef.current,
      JSON.stringify(requestPayload),
      'portfolio-cash',
    );
    cashOperationRef.current = attempt;
    setCashSubmitting(true);
    setCashError(null);
    setWriteWarning(null);
    try {
      await portfolioApi.createCashLedger({
        ...requestPayload,
        operationId: attempt.operationId,
      });
    } catch (err) {
      setCashError(getParsedApiError(err));
      setCashSubmitting(false);
      return;
    }
    cashOperationRef.current = null;
    setCashForm((prev) => ({ ...prev, note: '' }));
    setCashModalOpen(false);
    setCashSubmitting(false);
    await refreshPortfolioData();
  };

  const handleCorporateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) {
      setWriteWarning(text.selectAccountWrite);
      return;
    }
    if (
      corpForm.actionType === 'split_adjustment'
      && (!Number.isFinite(Number(corpForm.splitRatio)) || Number(corpForm.splitRatio) <= 0)
    ) {
      document.getElementById('portfolio-split-ratio')?.focus();
      return;
    }
    if (corpSubmitting) return;
    const requestPayload = {
      accountId: writableAccountId,
      symbol: corpForm.symbol,
      effectiveDate: corpForm.effectiveDate,
      actionType: corpForm.actionType,
      cashDividendPerShare: corpForm.cashDividendPerShare ? Number(corpForm.cashDividendPerShare) : undefined,
      splitRatio: corpForm.splitRatio ? Number(corpForm.splitRatio) : undefined,
      note: corpForm.note || undefined,
    };
    const attempt = resolveOperationAttempt(
      corporateOperationRef.current,
      JSON.stringify(requestPayload),
      'portfolio-corporate',
    );
    corporateOperationRef.current = attempt;
    setCorpSubmitting(true);
    setCorpError(null);
    setWriteWarning(null);
    try {
      await portfolioApi.createCorporateAction({
        ...requestPayload,
        operationId: attempt.operationId,
      });
    } catch (err) {
      setCorpError(getParsedApiError(err));
      setCorpSubmitting(false);
      return;
    }
    corporateOperationRef.current = null;
    setCorpForm((prev) => ({ ...prev, symbol: '', note: '' }));
    setCorpModalOpen(false);
    setCorpSubmitting(false);
    await refreshPortfolioData();
  };

  const handleParseCsv = async () => {
    if (!csvFile || !selectedBroker) return;
    try {
      setCsvParsing(true);
      setCsvError(null);
      const parsed = await portfolioApi.parseCsvImport(selectedBroker, csvFile);
      setCsvParseResult(parsed);
      setCsvCommitResult(null);
    } catch (err) {
      setCsvError(getParsedApiError(err));
    } finally {
      setCsvParsing(false);
    }
  };

  const handleCommitCsv = async () => {
    if (!csvFile || !selectedBroker) return;
    if (!writableAccountId) {
      setWriteWarning(text.selectAccountWrite);
      return;
    }
    const fingerprint = JSON.stringify({
      accountId: writableAccountId,
      broker: selectedBroker,
      dryRun: csvDryRun,
      file: {
        name: csvFile.name,
        size: csvFile.size,
        type: csvFile.type,
        lastModified: csvFile.lastModified,
      },
    });
    const attempt = resolveOperationAttempt(
      csvOperationRef.current,
      fingerprint,
      'portfolio-csv',
    );
    csvOperationRef.current = attempt;
    try {
      setWriteWarning(null);
      setCsvCommitting(true);
      setCsvError(null);
      const committed = await portfolioApi.commitCsvImport(
        writableAccountId,
        selectedBroker,
        csvFile,
        attempt.operationId,
        csvDryRun,
      );
      setCsvCommitResult(committed);
      if (committed.failedCount > 0) {
        // A replay of the same operation ID would permanently return the first
        // partial result. Start a new attempt so failed rows can run again;
        // stable trade UID/dedup hashes keep already-inserted rows idempotent.
        csvOperationRef.current = null;
      }
      if (!csvDryRun) {
        await refreshPortfolioData();
      }
    } catch (err) {
      setCsvError(getParsedApiError(err));
    } finally {
      setCsvCommitting(false);
    }
  };

  const openDeleteDialog = (item: PendingDelete) => {
    if (!writableAccountId) {
      setWriteWarning(text.selectAccountDeleteEntry);
      return;
    }
    setDeleteError(null);
    setPendingDelete(item);
  };

  const openAccountDeleteDialog = () => {
    if (!writableAccount) {
      setWriteWarning(text.selectAccountDeleteAccount);
      return;
    }
    setPendingAccountDelete({
      accountId: writableAccount.id,
      accountName: writableAccount.name,
    });
    setAccountDeleteError(null);
  };

  const handleConfirmAccountDelete = async () => {
    if (!pendingAccountDelete || accountDeleteLoading) return;

    try {
      setAccountDeleteLoading(true);
      setWriteWarning(null);
      await portfolioApi.deleteAccount(pendingAccountDelete.accountId);
      const nextAccount = accounts.find((item) => item.id !== pendingAccountDelete.accountId);
      setSelectedAccount(nextAccount?.id ?? 'all');
      setPendingAccountDelete(null);
      setAccountDeleteError(null);
      setShowCreateAccount(false);
      await loadAccounts();
      setEventPage(1);
    } catch (err) {
      setAccountDeleteError(getParsedApiError(err, language).message);
    } finally {
      setAccountDeleteLoading(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!pendingDelete || deleteLoading) return;
    if (!writableAccountId) {
      setWriteWarning(text.selectAccountDeleteEntry);
      setPendingDelete(null);
      setDeleteError(null);
      return;
    }

    const nextPage = currentEventCount === 1 && eventPage > 1 ? eventPage - 1 : eventPage;
    try {
      setDeleteLoading(true);
      setWriteWarning(null);
      if (pendingDelete.eventType === 'trade') {
        await portfolioApi.deleteTrade(pendingDelete.id);
      } else if (pendingDelete.eventType === 'cash') {
        await portfolioApi.deleteCashLedger(pendingDelete.id);
      } else {
        await portfolioApi.deleteCorporateAction(pendingDelete.id);
      }
      setPendingDelete(null);
      if (nextPage !== eventPage) {
        setEventPage(nextPage);
      }
      await refreshPortfolioData(nextPage);
    } catch (err) {
      setDeleteError(getParsedApiError(err, language).message);
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = accountForm.name.trim();
    if (!name) {
      setAccountCreateError(text.accountNameRequired);
      setAccountCreateSuccess(null);
      return;
    }
    try {
      setAccountCreating(true);
      setAccountCreateError(null);
      setAccountCreateSuccess(null);
      const created = await portfolioApi.createAccount({
        name,
        broker: accountForm.broker.trim() || undefined,
        market: accountForm.market,
        baseCurrency: accountForm.baseCurrency.trim() || 'CNY',
      });
      await loadAccounts();
      setSelectedAccount(created.id);
      setShowCreateAccount(false);
      setWriteWarning(null);
      setAccountForm({
        name: '',
        broker: 'Demo',
        market: accountForm.market,
        baseCurrency: accountForm.baseCurrency,
      });
      setAccountCreateSuccess(text.accountCreated);
    } catch (err) {
      setAccountCreateError(getParsedApiError(err, language).message || text.accountCreateFailed);
      setAccountCreateSuccess(null);
    } finally {
      setAccountCreating(false);
    }
  };

  const handleRefresh = async () => {
    await Promise.all([loadAccounts(), loadSnapshotAndRisk(), loadEvents(), loadBrokers()]);
    setPortfolioSignalsRefreshKey((current) => current + 1);
  };

  const reloadSnapshotAndRiskForScope = useCallback(async (
    requestedViewKey: string,
    requestedRequestId: number,
    requestedAccountId: number | undefined,
    requestedCostMethod: PortfolioCostMethod,
  ): Promise<boolean> => {
    if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
      return false;
    }

    setRiskWarning(null);

    try {
      const snapshotData = await portfolioApi.getSnapshot({
        accountId: requestedAccountId,
        costMethod: requestedCostMethod,
        includeRealtime: false,
      });
      if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return false;
      }
      setSnapshot(snapshotData);
      setError(null);

      try {
        const riskData = await portfolioApi.getRisk({
          accountId: requestedAccountId,
          costMethod: requestedCostMethod,
          includeRealtime: false,
        });
        if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
          return false;
        }
        setRisk(riskData);
        setRiskWarning(null);
      } catch (riskErr) {
        if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
          return false;
        }
        setRisk(null);
        setRiskWarning(getParsedApiError(riskErr, language).message || text.riskFallback);
      }
      return true;
    } catch (err) {
      if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return false;
      }
      setSnapshot(null);
      setRisk(null);
      setError(getParsedApiError(err));
      return false;
    }
  }, [language, text.riskFallback]);

  const handleRefreshFx = async () => {
    if (!hasAccounts || isLoading || fxRefreshing) {
      return;
    }

    const requestedViewKey = refreshViewKey;
    const requestedAccountId = queryAccountId;
    const requestedCostMethod = costMethod;
    const requestedRequestId = refreshContextRef.current.requestId + 1;
    refreshContextRef.current = {
      viewKey: requestedViewKey,
      requestId: requestedRequestId,
    };

    try {
      setFxRefreshing(true);
      setFxRefreshFeedback(null);
      const result = await portfolioApi.refreshFx({
        accountId: requestedAccountId,
      });
      if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return;
      }
      const reloaded = await reloadSnapshotAndRiskForScope(
        requestedViewKey,
        requestedRequestId,
        requestedAccountId,
        requestedCostMethod,
      );
      if (!reloaded || !isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return;
      }
      setFxRefreshFeedback(buildFxRefreshFeedback(result, language));
    } catch (err) {
      if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return;
      }
      setError(getParsedApiError(err));
    } finally {
      if (isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        setFxRefreshing(false);
      }
    }
  };

  const decisionSignalRiskPreviewItems = (risk?.decisionSignalRisk?.items ?? []).slice(0, 3);
  const formatDecisionSignalRiskAction = (signal: Partial<DecisionSignalItem>): string => (
    getDecisionActionLabel(
      signal.action,
      signal.actionLabel,
      null,
      text.alert,
      decisionActionLabels,
    ) ?? text.alert
  );
  const snapshotQualityMessage = snapshot?.dataQuality === 'partial' && snapshot.limitations?.length
    ? snapshot.limitations
      .map((limitation) => formatPortfolioLimitation(limitation, language))
      .join(getUiClauseSeparator(language))
    : null;

  return (
    <div className="portfolio-page min-h-dvh space-y-4 p-4 md:p-6">
      <section className="space-y-3">
        <div className="space-y-2">
          <h1 className="text-xl md:text-2xl font-semibold text-foreground">{text.title}</h1>
          <p className="text-xs md:text-sm text-secondary">
            {text.description}
          </p>
        </div>
        {hasAccounts ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_220px_280px] gap-2 items-end">
              <Select
                label={text.accountView}
                value={String(selectedAccount)}
                onChange={(value) => setSelectedAccount(value === 'all' ? 'all' : Number(value))}
                options={[
                  { value: 'all', label: text.allAccounts },
                  ...accounts.map((account) => ({ value: String(account.id), label: `${account.name} (#${account.id})` })),
                ]}
              />
              <Select
                label={text.costMethod}
                value={costMethod}
                onChange={(value) => setCostMethod(value as PortfolioCostMethod)}
                options={[
                  { value: 'fifo', label: text.fifo },
                  { value: 'avg', label: text.avg },
                ]}
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="comfortable"
                  className="flex-1"
                  onClick={() => {
                    setShowCreateAccount(true);
                    setAccountCreateError(null);
                    setAccountCreateSuccess(null);
                  }}
                >
                  {text.createAccount}
                </Button>
                <Button
                  type="button"
                  onClick={() => void handleRefresh()}
                  disabled={isLoading || fxRefreshing}
                  variant="secondary"
                  size="comfortable"
                  isLoading={isLoading}
                  loadingText={text.refreshing}
                  className="flex-1"
                >
                  {text.refreshData}
                </Button>
                <Button
                  type="button"
                  onClick={openAccountDeleteDialog}
                  disabled={!canDeleteSelectedAccount}
                  variant="danger-subtle"
                  size="comfortable"
                  isLoading={accountDeleteLoading}
                  loadingText={text.deletingAccount}
                  className="flex-1"
                >
                  {text.deleteAccount}
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <InlineAlert
            variant="warning"
            className="rounded-lg px-3 py-2 text-xs shadow-none"
            message={text.noAccounts}
            action={(
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  setShowCreateAccount(true);
                  setAccountCreateError(null);
                  setAccountCreateSuccess(null);
                }}
              >
                {text.addAccount}
              </Button>
            )}
          />
        )}
      </section>

      {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}
      {riskWarning ? (
        <InlineAlert
          variant="warning"
          title={text.riskDegraded}
          message={riskWarning}
        />
      ) : null}
      {writeWarning ? (
        <InlineAlert
          variant="warning"
          title={text.operationHint}
          message={writeWarning}
        />
      ) : null}
      {positionAnalysisMessage ? (
        <InlineAlert
          variant="success"
          title={text.analysisTask}
          message={positionAnalysisMessage}
        />
      ) : null}

      <Modal
        isOpen={showCreateAccount}
        onClose={() => setShowCreateAccount(false)}
        title={text.newAccount}
      >
          {!hasAccounts ? (
            <p className="mb-3 text-xs text-secondary">{text.createAutoSwitch}</p>
          ) : null}
          {accountCreateError ? (
            <InlineAlert
              variant="danger"
              className="mt-2 rounded-lg px-2 py-1 text-xs shadow-none"
              title={text.createFailed}
              message={accountCreateError}
            />
          ) : null}
          {accountCreateSuccess ? (
            <InlineAlert
              variant="success"
              className="mt-2 rounded-lg px-2 py-1 text-xs shadow-none"
              title={text.createSuccess}
              message={accountCreateSuccess}
            />
          ) : null}
          <form className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2" onSubmit={handleCreateAccount}>
            <Input
              label={text.accountName}
              placeholder={text.required}
              value={accountForm.name}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, name: e.target.value }))}
            />
            <Input
              label={text.broker}
              placeholder={text.brokerPlaceholder}
              value={accountForm.broker}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, broker: e.target.value }))}
            />
            <Input
              label={text.baseCurrency}
              placeholder={text.baseCurrencyPlaceholder}
              value={accountForm.baseCurrency}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, baseCurrency: e.target.value.toUpperCase() }))}
            />
            <Select
              label={text.market}
              value={accountForm.market}
              onChange={(value) => setAccountForm((prev) => ({ ...prev, market: value as PortfolioAccountMarket }))}
              options={[
                { value: 'cn', label: text.marketCn },
                { value: 'hk', label: text.marketHk },
                { value: 'us', label: text.marketUs },
                { value: 'jp', label: text.marketJp },
                { value: 'kr', label: text.marketKr },
                { value: 'tw', label: text.marketTw },
              ]}
            />
            <Button
              type="submit"
              variant="secondary"
              size="comfortable"
              className="md:col-span-2"
              isLoading={accountCreating}
              loadingText={text.creatingAccount}
            >
              {text.createAccount}
            </Button>
          </form>
      </Modal>

      {snapshotQualityMessage ? (
        <InlineAlert
          variant="warning"
          title={text.snapshotPartialTitle}
          message={snapshotQualityMessage}
          className="rounded-xl px-3 py-2 text-xs shadow-none"
        />
      ) : null}

      <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        <Card variant="gradient" padding="md">
          <p className="text-xs text-secondary">{text.totalEquity}</p>
          <p className="mt-1 text-xl font-semibold text-foreground">{formatMoney(snapshot?.totalEquity, snapshot?.currency || 'CNY', language)}</p>
        </Card>
        <Card variant="gradient" padding="md">
          <p className="text-xs text-secondary">{text.totalMarketValue}</p>
          <p className="mt-1 text-xl font-semibold text-foreground">{formatMoney(snapshot?.totalMarketValue, snapshot?.currency || 'CNY', language)}</p>
        </Card>
        <Card variant="gradient" padding="md">
          <p className="text-xs text-secondary">{text.totalCash}</p>
          <p className="mt-1 text-xl font-semibold text-foreground">{formatMoney(snapshot?.totalCash, snapshot?.currency || 'CNY', language)}</p>
        </Card>
        <Card variant="gradient" padding="md">
          <div className="flex items-start justify-between gap-3">
            <p className="text-xs text-secondary">{text.fxStatus}</p>
            <Button
              type="button"
              variant="secondary"
              size="comfortable"
              className="shrink-0 text-xs"
              onClick={() => void handleRefreshFx()}
              disabled={!hasAccounts || isLoading || fxRefreshing}
              isLoading={fxRefreshing}
              loadingText={text.refreshing}
            >
              {text.refreshFx}
            </Button>
          </div>
          <div className="mt-2">{snapshot?.fxStale ? <Badge variant="warning">{text.stale}</Badge> : <Badge variant="success">{text.latest}</Badge>}</div>
          {fxRefreshFeedback ? (
            <InlineAlert
              variant={getFxRefreshFeedbackVariant(fxRefreshFeedback.tone)}
              title={text.fxRefreshResult}
              message={fxRefreshFeedback.text}
              className="mt-3 rounded-xl px-3 py-2 text-xs shadow-none"
            />
          ) : null}
        </Card>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <Card className="xl:col-span-2" padding="md">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-foreground">{text.positionsTitle}</h2>
            <span className="text-xs text-secondary">{formatUiText(text.countItems, { count: positionRows.length })}</span>
          </div>
          {portfolioSignalsWarning ? (
            <InlineAlert
              variant="warning"
              title={t('decisionSignals.portfolioWarningTitle')}
              message={portfolioSignalsWarning}
              className="mb-3 rounded-xl px-3 py-2 text-xs shadow-none"
            />
          ) : null}
          {positionRows.length === 0 ? (
            <EmptyState
              title={text.noPositionsTitle}
              description={text.noPositionsDescription}
              className="border-none bg-transparent px-4 py-8 shadow-none"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-216 w-full text-sm">
                <thead className="text-xs text-secondary border-b border-white/10">
                  <tr>
                    <th className="text-left py-2 pr-2">{text.account}</th>
                    <th className="text-left py-2 pr-2">{text.code}</th>
                    <th className="text-right py-2 pr-2">{text.quantity}</th>
                    <th className="text-right py-2 pr-2">{text.avgCost}</th>
                    <th className="text-right py-2 pr-2">{text.lastPrice}</th>
                    <th className="text-right py-2 pr-2">{text.marketValue}</th>
                    <th className="text-right py-2 pr-3">{text.unrealizedPnl}</th>
                    <th className="text-right py-2 pr-3">{text.returnPct}</th>
                    <th className="min-w-[9rem] text-right py-2 pr-3">{t('decisionSignals.portfolioColumn')}</th>
                    <th className="w-20 text-right py-2">{text.action}</th>
                  </tr>
                </thead>
                <tbody>
                  {positionRows.map((row) => {
                    const rowKey = `${row.accountId}-${row.symbol}-${row.market}`;
                    const analyzing = positionAnalysisLoadingKey === rowKey;
                    const signal = signalByPositionKey.get(rowKey);
                    return (
                    <tr key={rowKey} className="border-b border-white/5">
                      <td className="py-2 pr-2 text-secondary">{row.accountName}</td>
                      <td className="py-2 pr-2 font-mono text-foreground">{row.symbol}</td>
                      <td className="py-2 pr-2 text-right">{row.quantity.toFixed(2)}</td>
                      <td className="py-2 pr-2 text-right">{row.avgCost.toFixed(4)}</td>
                      <td className="py-2 pr-2 text-right">
                        <div>{formatPositionPrice(row)}</div>
                        <div className={`text-xs ${hasPositionPrice(row) ? 'text-secondary' : 'text-warning'}`}>
                          {getPositionPriceLabel(row, language)}
                        </div>
                      </td>
                      <td className="py-2 pr-2 text-right">{formatPositionMoney(row.marketValueBase, row, language)}</td>
                      <td
                        className={`py-2 pr-3 text-right ${
                          hasPositionPrice(row)
                            ? row.unrealizedPnlBase >= 0
                              ? 'text-success'
                              : 'text-danger'
                            : 'text-secondary'
                        }`}
                      >
                        {formatPositionMoney(row.unrealizedPnlBase, row, language)}
                      </td>
                      <td
                        className={`py-2 pr-3 text-right ${
                          hasPositionPrice(row) && row.unrealizedPnlPct !== null && row.unrealizedPnlPct !== undefined
                            ? row.unrealizedPnlPct >= 0
                              ? 'text-success'
                              : 'text-danger'
                            : 'text-secondary'
                        }`}
                      >
                        {formatSignedPct(row.unrealizedPnlPct)}
                      </td>
                      <td className="py-2 pr-3 text-right align-top">
                        <PortfolioSignalSummary item={signal} loading={portfolioSignalsLoading} />
                      </td>
                      <td className="py-2 text-right">
                        <Button
                          type="button"
                          onClick={() => void handleAnalyzePosition(row)}
                          disabled={analyzing}
                          variant="secondary"
                          size="comfortable"
                          isLoading={analyzing}
                          loadingText={text.submitting}
                          className="text-xs"
                        >
                          {text.analyze}
                        </Button>
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card padding="md">
          <h2 className="text-sm font-semibold text-foreground mb-3">
            {concentrationMode === 'sector' ? text.sectorConcentration : text.positionConcentrationFallback}
          </h2>
          {concentrationPieData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={concentrationPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90}>
                    {concentrationPieData.map((entry, index) => (
                      <Cell key={`cell-${entry.name}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              title={text.noConcentrationTitle}
              description={text.noConcentrationDescription}
              className="border-none bg-transparent px-4 py-10 shadow-none"
            />
          )}
          <div className="mt-3 text-xs text-secondary space-y-1">
            <div>{text.displayScope}: {concentrationMode === 'sector' ? text.sectorDimension : text.positionDimensionFallback}</div>
            <div>{text.sectorAlert}: {risk?.sectorConcentration?.alert ? text.yes : text.no}</div>
            <div>{text.topWeight}: {formatPct(risk?.sectorConcentration?.topWeightPct ?? risk?.concentration?.topWeightPct)}</div>
          </div>
        </Card>
      </section>

      {writeBlocked && hasAccounts ? (
        <InlineAlert
          variant="warning"
          className="rounded-lg px-3 py-2 text-xs shadow-none"
          message={text.writeBlocked}
        />
      ) : null}

      <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        <Card padding="md">
          <h3 className="text-sm font-semibold text-foreground mb-2">{text.drawdownMonitor}</h3>
          <div className="text-xs text-secondary space-y-1">
            <div>{text.maxDrawdown}: {formatPct(risk?.drawdown?.maxDrawdownPct)}</div>
            <div>{text.currentDrawdown}: {formatPct(risk?.drawdown?.currentDrawdownPct)}</div>
            <div>{text.alert}: {risk?.drawdown?.alert ? text.yes : text.no}</div>
          </div>
        </Card>
        <Card padding="md">
          <h3 className="text-sm font-semibold text-foreground mb-2">{text.stopLossWarning}</h3>
          <div className="text-xs text-secondary space-y-1">
            <div>{text.triggeredCount}: {risk?.stopLoss?.triggeredCount ?? 0}</div>
            <div>{text.nearCount}: {risk?.stopLoss?.nearCount ?? 0}</div>
            <div>{text.alert}: {risk?.stopLoss?.nearAlert ? text.yes : text.no}</div>
          </div>
        </Card>
        <Card padding="md">
          <h3 className="text-sm font-semibold text-foreground mb-2">{text.scope}</h3>
          <div className="text-xs text-secondary space-y-1">
            <div>{text.accountCount}: {snapshot?.accountCount ?? 0}</div>
            <div>{text.currency}: {snapshot?.currency || 'CNY'}</div>
            <div>{text.costMethodShort}: {(snapshot?.costMethod || costMethod).toUpperCase()}</div>
          </div>
        </Card>
        <Card padding="md">
          <h3 className="text-sm font-semibold text-foreground mb-2">{text.aiRiskSignals}</h3>
          <div className="text-xs text-secondary space-y-1">
            {risk?.decisionSignalRisk?.available === false ? (
              <div className="text-warning">{text.aiRiskUnavailable}</div>
            ) : (
              <>
                <div>{text.aiRiskTotal}: {risk?.decisionSignalRisk?.total ?? 0}</div>
                <div>
                  {text.sellSignals}: {risk?.decisionSignalRisk?.actions?.sell ?? 0} · {text.reduceSignals}: {risk?.decisionSignalRisk?.actions?.reduce ?? 0} · {text.alertSignals}: {risk?.decisionSignalRisk?.actions?.alert ?? 0}
                </div>
                {decisionSignalRiskPreviewItems.length > 0 ? (
                  <div className="space-y-1 pt-1">
                    {decisionSignalRiskPreviewItems.map((item) => (
                      <div key={`${item.accountId ?? 'all'}-${item.market}-${item.symbol}-${item.signal.id ?? item.signal.action}`} className="truncate text-foreground">
                        {item.symbol} · {formatDecisionSignalRiskAction(item.signal)}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div>{text.noAiRiskSignals}</div>
                )}
              </>
            )}
          </div>
        </Card>
      </section>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" size="comfortable" onClick={() => setTradeModalOpen(true)} disabled={!writableAccountId}>{text.enterTrade}</Button>
        <Button type="button" variant="secondary" size="comfortable" onClick={() => setCashModalOpen(true)} disabled={!writableAccountId}>{text.enterCash}</Button>
        <Button type="button" variant="secondary" size="comfortable" onClick={() => setCorpModalOpen(true)} disabled={!writableAccountId}>{text.enterCorporate}</Button>
        <Button type="button" variant="secondary" size="md" className="text-xs" onClick={() => setCsvModalOpen(true)}>{text.csvImport}</Button>
        <Button type="button" variant="secondary" size="comfortable" onClick={() => setEventModalOpen(true)}>{text.eventLog}</Button>
      </div>

      <Modal isOpen={tradeModalOpen} closeDisabled={tradeSubmitting} onClose={() => { setTradeError(null); setTradeModalOpen(false); }} title={text.manualTrade}>
          <form onSubmit={handleTradeSubmit} aria-busy={tradeSubmitting}>
            <fieldset disabled={tradeSubmitting} className="m-0 min-w-0 space-y-2 border-0 p-0">
            <Input
              label={text.stockCode}
              placeholder={text.stockExample}
              value={tradeForm.symbol}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, symbol: e.target.value }))}
              required
            />
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <DatePicker
                label={text.tradeDate}
                value={tradeForm.tradeDate}
                onChange={(tradeDate) => setTradeForm((prev) => ({ ...prev, tradeDate }))}
                required
                className="w-full"
                triggerClassName={PORTFOLIO_DATE_TRIGGER_CLASS}
              />
              <Select
                label={text.side}
                value={tradeForm.side}
                disabled={tradeSubmitting}
                onChange={(value) => setTradeForm((prev) => ({ ...prev, side: value as PortfolioSide }))}
                options={[
                  { value: 'buy', label: text.buy },
                  { value: 'sell', label: text.sell },
                ]}
              />
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Input id="portfolio-trade-quantity" label={text.quantity} type="number" min="0.0001" step="0.0001" placeholder={text.required} value={tradeForm.quantity}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, quantity: e.target.value }))} required />
              <Input id="portfolio-trade-price" label={text.tradePrice} type="number" min="0.0001" step="0.0001" placeholder={text.required} value={tradeForm.price}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, price: e.target.value }))} required />
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Input label={text.fee} type="number" min="0" step="0.0001" placeholder={text.optional} value={tradeForm.fee}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, fee: e.target.value }))} />
              <Input label={text.tax} type="number" min="0" step="0.0001" placeholder={text.optional} value={tradeForm.tax}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, tax: e.target.value }))} />
            </div>
            <p className="text-xs text-secondary">{text.feeHint}</p>
            {tradeError ? (
              <ApiErrorAlert error={tradeError} onDismiss={() => setTradeError(null)} />
            ) : null}
            <Button type="submit" variant="secondary" size="comfortable" className="w-full" disabled={!writableAccountId} isLoading={tradeSubmitting} loadingText={text.submitting}>
              {text.submitTrade}
            </Button>
            </fieldset>
          </form>
      </Modal>

      <Modal isOpen={cashModalOpen} closeDisabled={cashSubmitting} onClose={() => { setCashError(null); setCashModalOpen(false); }} title={text.manualCash}>
          <form onSubmit={handleCashSubmit} aria-busy={cashSubmitting}>
            <fieldset disabled={cashSubmitting} className="m-0 min-w-0 space-y-2 border-0 p-0">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <DatePicker
                label={text.date}
                value={cashForm.eventDate}
                onChange={(eventDate) => setCashForm((prev) => ({ ...prev, eventDate }))}
                required
                className="w-full"
                triggerClassName={PORTFOLIO_DATE_TRIGGER_CLASS}
              />
              <Select
                label={text.direction}
                value={cashForm.direction}
                disabled={cashSubmitting}
                onChange={(value) => setCashForm((prev) => ({ ...prev, direction: value as PortfolioCashDirection }))}
                options={[
                  { value: 'in', label: text.inflow },
                  { value: 'out', label: text.outflow },
                ]}
              />
            </div>
            <Input id="portfolio-cash-amount" label={text.amount} type="number" min="0.0001" step="0.0001" placeholder={text.amount}
              value={cashForm.amount} onChange={(e) => setCashForm((prev) => ({ ...prev, amount: e.target.value }))} required />
            <Input label={text.currency} placeholder={formatUiText(text.defaultCurrency, { currency: writableAccount?.baseCurrency || text.accountBaseCurrency })} value={cashForm.currency}
              onChange={(e) => setCashForm((prev) => ({ ...prev, currency: e.target.value }))} />
            {cashError ? (
              <ApiErrorAlert error={cashError} onDismiss={() => setCashError(null)} />
            ) : null}
            <Button type="submit" variant="secondary" size="comfortable" className="w-full" disabled={!writableAccountId} isLoading={cashSubmitting} loadingText={text.submitting}>
              {text.submitCash}
            </Button>
            </fieldset>
          </form>
      </Modal>

      <Modal isOpen={corpModalOpen} closeDisabled={corpSubmitting} onClose={() => { setCorpError(null); setCorpModalOpen(false); }} title={text.manualCorporate}>
          <form onSubmit={handleCorporateSubmit} aria-busy={corpSubmitting}>
            <fieldset disabled={corpSubmitting} className="m-0 min-w-0 space-y-2 border-0 p-0">
            <Input label={text.stockCode} placeholder={text.stockCode} value={corpForm.symbol}
              onChange={(e) => setCorpForm((prev) => ({ ...prev, symbol: e.target.value }))} required />
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <DatePicker
                label={text.effectiveDate}
                value={corpForm.effectiveDate}
                onChange={(effectiveDate) => setCorpForm((prev) => ({ ...prev, effectiveDate }))}
                required
                className="w-full"
                triggerClassName={PORTFOLIO_DATE_TRIGGER_CLASS}
              />
              <Select
                label={text.actionType}
                value={corpForm.actionType}
                disabled={corpSubmitting}
                onChange={(value) => setCorpForm((prev) => ({ ...prev, actionType: value as PortfolioCorporateActionType }))}
                options={[
                  { value: 'cash_dividend', label: text.cashDividend },
                  { value: 'split_adjustment', label: text.splitAdjustment },
                ]}
              />
            </div>
            {corpForm.actionType === 'cash_dividend' ? (
              <Input label={text.dividendPerShare} type="number" min="0" step="0.000001" placeholder={text.dividendPerShare}
                value={corpForm.cashDividendPerShare}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, cashDividendPerShare: e.target.value, splitRatio: '' }))} required />
            ) : (
              <Input id="portfolio-split-ratio" label={text.splitRatio} type="number" min="0.000001" step="0.000001" placeholder={text.splitRatio}
                value={corpForm.splitRatio}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, splitRatio: e.target.value, cashDividendPerShare: '' }))} required />
            )}
            {corpError ? (
              <ApiErrorAlert error={corpError} onDismiss={() => setCorpError(null)} />
            ) : null}
            <Button type="submit" variant="secondary" size="comfortable" className="w-full" disabled={!writableAccountId} isLoading={corpSubmitting} loadingText={text.submitting}>
              {text.submitCorporate}
            </Button>
            </fieldset>
          </form>
      </Modal>

      <Modal
        isOpen={csvModalOpen}
        closeDisabled={csvParsing || csvCommitting}
        onClose={() => {
          setCsvError(null);
          setCsvModalOpen(false);
        }}
        title={text.csvImport}
      >
          <fieldset
            disabled={csvParsing || csvCommitting}
            aria-busy={csvParsing || csvCommitting}
            className="m-0 min-w-0 space-y-2 border-0 p-0"
          >
            {brokerLoadWarning ? (
              <InlineAlert
                variant="warning"
                className="rounded-lg px-2 py-1 text-xs shadow-none"
                message={brokerLoadWarning}
              />
            ) : null}
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Select
                label={text.broker}
                value={selectedBroker}
                onChange={(value) => {
                  setSelectedBroker(value);
                  csvOperationRef.current = null;
                  setCsvCommitResult(null);
                }}
                disabled={csvParsing || csvCommitting || brokers.length === 0}
                options={brokers.map((item) => ({ value: item.broker, label: formatBrokerLabel(item.broker, item.displayName, language) }))}
              />
              <div className="space-y-1">
                <span className="block text-xs text-muted-text">{text.csvFile}</span>
                <label className={PORTFOLIO_FILE_PICKER_CLASS}>
                  {text.chooseCsv}
                  <input ref={csvInputRef} type="file" accept=".csv" className="hidden"
                    onChange={(e) => {
                      setCsvFile(e.target.files && e.target.files[0] ? e.target.files[0] : null);
                      csvOperationRef.current = null;
                      setCsvParseResult(null);
                      setCsvCommitResult(null);
                    }} />
                </label>
                {csvFile ? (
                  <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-surface px-2 py-1.5">
                    <span className="min-w-0 flex-1 truncate text-xs text-foreground">{csvFile.name}</span>
                    <span className="shrink-0 text-xs text-muted-text">
                      {formatUiText(fileText.size, { size: Math.max(0.1, csvFile.size / 1024).toFixed(1) })}
                    </span>
                    <IconButton
                      type="button"
                      variant="ghost"
                      size="default"
                      aria-label={fileText.clear}
                      onClick={() => {
                        setCsvFile(null);
                        if (csvInputRef.current) csvInputRef.current.value = '';
                        csvOperationRef.current = null;
                        setCsvParseResult(null);
                        setCsvCommitResult(null);
                      }}
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </IconButton>
                  </div>
                ) : null}
              </div>
            </div>
            <Checkbox
              id="csv-dry-run"
              checked={csvDryRun}
              onChange={(event) => {
                setCsvDryRun(event.target.checked);
                csvOperationRef.current = null;
              }}
              containerClassName="min-h-11 text-xs text-secondary"
              label={<span className="text-xs font-normal text-secondary-text">{text.dryRun}</span>}
            />
            <div className="flex gap-2">
              <Button type="button" variant="secondary" size="comfortable" className="flex-1" disabled={!selectedBroker || !csvFile || csvCommitting} isLoading={csvParsing} loadingText={text.parsing} onClick={() => void handleParseCsv()}>
                {text.parseFile}
              </Button>
              <Button type="button" variant="secondary" size="comfortable" className="flex-1"
                disabled={!selectedBroker || !csvFile || !writableAccountId || csvParsing} isLoading={csvCommitting} loadingText={text.submitting} onClick={() => void handleCommitCsv()}>
                {text.commitImport}
              </Button>
            </div>
            {csvError ? (
              <ApiErrorAlert error={csvError} onDismiss={() => setCsvError(null)} />
            ) : null}
            {csvParseResult ? (
              <InlineAlert
                variant={getCsvParseVariant(csvParseResult)}
                title={text.csvParseResult}
                message={formatUiText(text.csvParseSummary, { valid: csvParseResult.recordCount, skipped: csvParseResult.skippedCount, errors: csvParseResult.errorCount })}
                className="rounded-lg px-3 py-2 text-xs shadow-none"
              />
            ) : null}
            {csvCommitResult ? (
              <InlineAlert
                variant={getCsvCommitVariant(csvCommitResult, csvCommitResult.dryRun)}
                title={csvCommitResult.dryRun ? text.csvDryResult : text.csvCommitResult}
                message={formatUiText(text.csvCommitSummary, { mode: csvCommitResult.dryRun ? text.dryCheck : text.actualWrite, inserted: csvCommitResult.insertedCount, duplicates: csvCommitResult.duplicateCount, failed: csvCommitResult.failedCount })}
                className="rounded-lg px-3 py-2 text-xs shadow-none"
              />
            ) : null}
          </fieldset>
      </Modal>

      <Modal isOpen={eventModalOpen} onClose={() => { setEventError(null); setEventModalOpen(false); }} title={text.eventLog}>
          <div className="space-y-2">
            <div className="grid grid-cols-1 items-end gap-2 sm:grid-cols-2">
              <Select
                label={text.type}
                value={eventType}
                onChange={(value) => setEventType(value as EventType)}
                options={[
                  { value: 'trade', label: text.tradeLedger },
                  { value: 'cash', label: text.cashLedger },
                  { value: 'corporate', label: text.corporateAction },
                ]}
              />
              <Button type="button" variant="secondary" size="comfortable" onClick={applyEventFilters} isLoading={eventLoading} loadingText={text.loading}>
                {text.refreshLedger}
              </Button>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <DatePicker
                label={text.startDate}
                value={eventDateFrom}
                onChange={setEventDateFrom}
                className="w-full"
                triggerClassName={PORTFOLIO_DATE_TRIGGER_CLASS}
              />
              <DatePicker
                label={text.endDate}
                value={eventDateTo}
                onChange={setEventDateTo}
                className="w-full"
                triggerClassName={PORTFOLIO_DATE_TRIGGER_CLASS}
              />
            </div>
            {(eventType === 'trade' || eventType === 'corporate') ? (
              <Input label={text.stockCode} placeholder={text.stockFilter} value={eventSymbol}
                onChange={(e) => setEventSymbol(e.target.value)} />
            ) : null}
            {eventType === 'trade' ? (
              <Select
                ariaLabel={text.side}
                value={eventSide}
                onChange={(value) => setEventSide(value as '' | PortfolioSide)}
                options={[
                  { value: '', label: text.allSides },
                  { value: 'buy', label: text.buy },
                  { value: 'sell', label: text.sell },
                ]}
              />
            ) : null}
            {eventType === 'cash' ? (
              <Select
                ariaLabel={text.direction}
                value={eventDirection}
                onChange={(value) => setEventDirection(value as '' | PortfolioCashDirection)}
                options={[
                  { value: '', label: text.allCashDirections },
                  { value: 'in', label: text.inflow },
                  { value: 'out', label: text.outflow },
                ]}
              />
            ) : null}
            {eventType === 'corporate' ? (
              <Select
                ariaLabel={text.actionType}
                value={eventActionType}
                onChange={(value) => setEventActionType(value as '' | PortfolioCorporateActionType)}
                options={[
                  { value: '', label: text.allCorporateActions },
                  { value: 'cash_dividend', label: text.cashDividend },
                  { value: 'split_adjustment', label: text.splitAdjustment },
                ]}
              />
            ) : null}
            <div className="text-xs text-secondary">
              {writeBlocked ? text.deleteBlocked : text.deleteHint}
            </div>
            {eventError ? (
              <ApiErrorAlert
                error={eventError}
                actionLabel={t('common.retry')}
                onAction={applyEventFilters}
                onDismiss={() => setEventError(null)}
              />
            ) : null}
            <div className="max-h-64 overflow-auto rounded-lg border border-white/10 p-2">
              {eventType === 'trade' && tradeEvents.map((item) => (
                <div key={`t-${item.id}`} className="flex items-start justify-between gap-3 border-b border-white/5 py-2 text-xs text-secondary">
                  <div className="min-w-0">
                    {formatUiText(text.tradeRow, { date: item.tradeDate, side: formatSideLabel(item.side, language), symbol: item.symbol, quantity: item.quantity, price: item.price })}
                  </div>
                  {!writeBlocked ? (
                    <Button
                      type="button"
                      variant="danger-subtle"
                      size="comfortable"
                      className="shrink-0 text-xs"
                      onClick={() => openDeleteDialog({
                        eventType: 'trade',
                        id: item.id,
                        message: formatUiText(text.deleteTradeMessage, { date: item.tradeDate, side: formatSideLabel(item.side, language), symbol: item.symbol, quantity: item.quantity, price: item.price }),
                      })}
                    >
                      {t('common.delete')}
                    </Button>
                  ) : null}
                </div>
              ))}
              {eventType === 'cash' && cashEvents.map((item) => (
                <div key={`c-${item.id}`} className="flex items-start justify-between gap-3 border-b border-white/5 py-2 text-xs text-secondary">
                  <div className="min-w-0">
                    {item.eventDate} {formatCashDirectionLabel(item.direction, language)} {item.amount} {item.currency}
                  </div>
                  {!writeBlocked ? (
                    <Button
                      type="button"
                      variant="danger-subtle"
                      size="comfortable"
                      className="shrink-0 text-xs"
                      onClick={() => openDeleteDialog({
                        eventType: 'cash',
                        id: item.id,
                        message: formatUiText(text.deleteCashMessage, { date: item.eventDate, direction: formatCashDirectionLabel(item.direction, language), amount: item.amount, currency: item.currency }),
                      })}
                    >
                      {t('common.delete')}
                    </Button>
                  ) : null}
                </div>
              ))}
              {eventType === 'corporate' && corporateEvents.map((item) => (
                <div key={`ca-${item.id}`} className="flex items-start justify-between gap-3 border-b border-white/5 py-2 text-xs text-secondary">
                  <div className="min-w-0">
                    {item.effectiveDate} {formatCorporateActionLabel(item.actionType, language)} {item.symbol}
                  </div>
                  {!writeBlocked ? (
                    <Button
                      type="button"
                      variant="danger-subtle"
                      size="comfortable"
                      className="shrink-0 text-xs"
                      onClick={() => openDeleteDialog({
                        eventType: 'corporate',
                        id: item.id,
                        message: formatUiText(text.deleteCorporateMessage, { date: item.effectiveDate, action: formatCorporateActionLabel(item.actionType, language), symbol: item.symbol }),
                      })}
                    >
                      {t('common.delete')}
                    </Button>
                  ) : null}
                </div>
              ))}
              {!eventLoading
                && ((eventType === 'trade' && tradeEvents.length === 0)
                  || (eventType === 'cash' && cashEvents.length === 0)
                  || (eventType === 'corporate' && corporateEvents.length === 0)) ? (
                    <EmptyState
                      title={text.noLedger}
                      description={text.noLedgerDescription}
                      className="border-none bg-transparent px-3 py-6 shadow-none"
                    />
                  ) : null}
            </div>
            <div className="flex items-center justify-between text-xs text-secondary">
              <span>{formatUiText(text.page, { page: eventPage, pages: totalEventPages })}</span>
              <div className="flex gap-2">
                <Button type="button" variant="secondary" size="comfortable" className="text-xs" disabled={eventPage <= 1}
                  onClick={() => setEventPage((prev) => Math.max(1, prev - 1))}>
                  {text.prevPage}
                </Button>
                <Button type="button" variant="secondary" size="comfortable" className="text-xs" disabled={eventPage >= totalEventPages}
                  onClick={() => setEventPage((prev) => Math.min(totalEventPages, prev + 1))}>
                  {text.nextPage}
                </Button>
              </div>
            </div>
          </div>
      </Modal>
      <ConfirmDialog
        isOpen={Boolean(pendingDelete)}
        title={text.deleteEntryTitle}
        message={pendingDelete?.message || text.deleteEntryDefault}
        confirmText={deleteLoading ? text.deletingEntry : text.confirmDelete}
        cancelText={t('common.cancel')}
        isDanger
        confirmDisabled={deleteLoading}
        cancelDisabled={deleteLoading}
        error={deleteError}
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => {
          if (!deleteLoading) {
            setPendingDelete(null);
            setDeleteError(null);
          }
        }}
      />
      <ConfirmDialog
        isOpen={Boolean(pendingAccountDelete)}
        title={text.deleteAccountTitle}
        message={
          pendingAccountDelete
            ? formatUiText(text.deleteAccountMessage, {
              name: pendingAccountDelete.accountName,
              id: pendingAccountDelete.accountId,
            })
            : ''
        }
        confirmText={accountDeleteLoading ? text.deletingAccount : text.deleteAccountConfirm}
        isDanger
        confirmDisabled={accountDeleteLoading}
        cancelDisabled={accountDeleteLoading}
        error={accountDeleteError}
        onConfirm={() => void handleConfirmAccountDelete()}
        onCancel={() => {
          if (!accountDeleteLoading) {
            setPendingAccountDelete(null);
            setAccountDeleteError(null);
          }
        }}
      />
    </div>
  );
};

export default PortfolioPage;
