// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Portfolio route workspace — feature-owned composition for PortfolioPage.

import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pie, PieChart, ResponsiveContainer, Tooltip, Legend, Cell } from 'recharts';
import { BriefcaseBusiness, Inbox, X } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { portfolioApi } from '../../api/portfolio';
import type { ParsedApiError } from '../../api/error';
import { getParsedApiError } from '../../api/error';
import { AnalysisPhaseSelect } from '../analysis';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Checkbox, ConfirmDialog, DataTable, type DataTableColumn, DatePicker, EmptyState, FileInput, IconButton, InlineAlert, Input, Loading, Modal, PageHeader, Select, Surface } from '../common';
import { PortfolioSignalSummary } from '../decision-signals/DecisionSignalDisplay';
import { RunFlowPanel } from '../run-flow';
import { TaskPanel } from '../tasks';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { getUiClauseSeparator } from '../../utils/uiLocale';
import { formatUiText } from '../../i18n/uiText';
import { PORTFOLIO_FILE_TEXT, PORTFOLIO_TEXT } from '../../locales/portfolio';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  buildAnalysisWorkbenchHref,
} from '../../routing/routes';
import { usePortfolioAnalysisTasks } from './usePortfolioAnalysisTasks';
import {
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
  hasPositionPrice,
} from '../../utils/portfolioFormat';
import type {
  DecisionSignalItem,
} from '../../types/decisionSignals';
import type {
  AnalysisPhase,
} from '../../types/analysis';
import type {
  PortfolioAccountItem,
  PortfolioAccountType,
  PortfolioCashDirection,
  PortfolioCorporateActionType,
  PortfolioCostMethod,
  PortfolioSide,
} from '../../types/portfolio';
import { buildDecisionActionLabelMap } from '../../utils/decisionAction';
import { getDecisionSignalPresentation } from '../../utils/decisionSignalPresentation';
import { parseDeepLink } from '../../utils/deepLink';
import {
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  buildSignalCenterHref,
} from '../../routing/routes';
import {
  type PortfolioEventType,
  usePortfolioProjectionSession,
} from '../../hooks/portfolio/usePortfolioProjectionSession';
import { usePortfolioLedgerMutationWorkflow } from '../../hooks/portfolio/usePortfolioLedgerMutationWorkflow';
import { usePortfolioHoldingSignals } from '../../hooks/portfolio/usePortfolioHoldingSignals';
import { usePortfolioLedgerEntryForms } from '../../hooks/portfolio/usePortfolioLedgerEntryForms';
import { usePortfolioCsvImportSession } from '../../hooks/portfolio/usePortfolioCsvImportSession';
import { formatPortfolioLimitation } from '../../hooks/portfolio/helpers';
import { PIE_COLORS, PORTFOLIO_DATE_TRIGGER_CLASS } from '../../hooks/portfolio/constants';
import type {
  AccountOption,
  FlatPosition,
  PendingAccountDelete,
  PendingDelete,
  PortfolioAccountMarket,
} from '../../hooks/portfolio/types';

const PortfolioWorkspace: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { language, t } = useUiLanguage();
  const text = PORTFOLIO_TEXT[language];
  const fileText = PORTFOLIO_FILE_TEXT[language];
  const decisionActionLabels = useMemo(() => buildDecisionActionLabelMap(t), [t]);

  // Set page title
  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const parsedPortfolioLink = useMemo(
    () => parseDeepLink(`/portfolio${searchParams.size ? `?${searchParams.toString()}` : ''}`),
    [searchParams],
  );
  const requestedAccountId = parsedPortfolioLink.target?.page === 'portfolio'
    ? parsedPortfolioLink.target.accountId
    : undefined;
  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [accountsLoaded, setAccountsLoaded] = useState(false);
  const [selectedAccount, setSelectedAccountState] = useState<AccountOption>(requestedAccountId ?? 'all');
  const [unavailableAccountId, setUnavailableAccountId] = useState<number | null>(null);
  const selectedAccountRef = useRef<AccountOption>(selectedAccount);
  const searchParamsRef = useRef(searchParams);
  const setSearchParamsRef = useRef(setSearchParams);
  searchParamsRef.current = searchParams;
  setSearchParamsRef.current = setSearchParams;
  const [showCreateAccount, setShowCreateAccount] = useState(false);
  const [eventModalOpen, setEventModalOpen] = useState(false);
  const [accountCreating, setAccountCreating] = useState(false);
  const [accountCreateError, setAccountCreateError] = useState<string | null>(null);
  const [accountCreateSuccess, setAccountCreateSuccess] = useState<string | null>(null);
  const [editingAccountId, setEditingAccountId] = useState<number | null>(null);
  const [accountForm, setAccountForm] = useState({
    name: '',
    broker: 'Demo',
    market: 'cn' as PortfolioAccountMarket,
    baseCurrency: 'CNY',
    accountType: 'real' as PortfolioAccountType,
  });
  const [costMethod, setCostMethod] = useState<PortfolioCostMethod>('fifo');
  const [positionAnalysisPhase, setPositionAnalysisPhase] = useState<AnalysisPhase>('auto');
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [writeWarning, setWriteWarning] = useState<string | null>(null);
  const [positionAnalysisLoadingKey, setPositionAnalysisLoadingKey] = useState<string | null>(null);
  const {
    tasks: portfolioAnalysisTasks,
    acceptTask: acceptPortfolioAnalysisTask,
    attachExistingTask: attachPortfolioAnalysisTask,
    dismissTask: dismissPortfolioAnalysisTask,
    openRunFlow: openPortfolioRunFlow,
    closeRunFlow: closePortfolioRunFlow,
    runFlowDialog: portfolioRunFlowDialog,
  } = usePortfolioAnalysisTasks({
    searchParams,
    setSearchParams,
  });


  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [pendingAccountDelete, setPendingAccountDelete] = useState<PendingAccountDelete | null>(null);
  const [accountDeleteLoading, setAccountDeleteLoading] = useState(false);
  const [accountDeleteError, setAccountDeleteError] = useState<string | null>(null);


  const queryAccountId = selectedAccount === 'all' ? undefined : selectedAccount;
  const hasAccounts = accounts.length > 0;
  const writableAccount = selectedAccount === 'all' ? undefined : accounts.find((item) => item.id === selectedAccount);
  const writableAccountId = writableAccount?.id;
  const writableAccountType = writableAccount?.accountType ?? 'real';
  const isPaperAccountSelected = Boolean(writableAccount) && writableAccountType === 'paper';
  const writeBlocked = !writableAccountId;

  const setSelectedAccount = useCallback((
    account: AccountOption,
    replace = false,
    unavailableId: number | null = null,
  ) => {
    selectedAccountRef.current = account;
    setSelectedAccountState(account);
    setUnavailableAccountId(unavailableId);
    const next = new URLSearchParams(searchParamsRef.current);
    if (account === 'all') next.delete('account');
    else next.set('account', String(account));
    setSearchParamsRef.current(next, { replace });
  }, []);

  useEffect(() => {
    const nextAccount = requestedAccountId ?? 'all';
    if (selectedAccountRef.current !== nextAccount) {
      selectedAccountRef.current = nextAccount;
      setSelectedAccountState(nextAccount);
    }
  }, [requestedAccountId]);

  useEffect(() => {
    const currentSearch = searchParams.toString();
    const normalizedSearch = parsedPortfolioLink.normalizedSearch.replace(/^\?/, '');
    if (normalizedSearch !== currentSearch) {
      setSearchParams(new URLSearchParams(normalizedSearch), { replace: true });
    }
  }, [parsedPortfolioLink.normalizedSearch, searchParams, setSearchParams]);

  useEffect(() => {
    if (
      !accountsLoaded
      || requestedAccountId === undefined
      || accounts.some((account) => account.id === requestedAccountId)
    ) {
      return;
    }
    setSelectedAccount(accounts[0]?.id ?? 'all', true, requestedAccountId);
  }, [accounts, accountsLoaded, requestedAccountId, setSelectedAccount]);

  const loadAccounts = useCallback(async (): Promise<boolean> => {
    try {
      const response = await portfolioApi.getAccounts(false);
      const items = response.accounts || [];
      setAccounts(items);
      const currentAccount = selectedAccountRef.current;
      if (items.length === 0) {
        if (currentAccount !== 'all') setSelectedAccount('all', true, currentAccount);
      } else if (currentAccount !== 'all' && !items.some((item) => item.id === currentAccount)) {
        setSelectedAccount(items[0].id, true, currentAccount);
      }
      return true;
    } catch (err) {
      setError(getParsedApiError(err));
      return false;
    } finally {
      setAccountsLoaded(true);
    }
  }, [setSelectedAccount]);


  const {
    snapshot,
    risk,
    isLoading,
    riskWarning,
    fxRefreshing,
    fxRefreshFeedback,
    handleRefreshFx,
    loadSnapshotAndRisk,
    eventType,
    setEventType,
    eventDateFrom,
    setEventDateFrom,
    eventDateTo,
    setEventDateTo,
    eventSymbol,
    setEventSymbol,
    eventSide,
    setEventSide,
    eventDirection,
    setEventDirection,
    eventActionType,
    setEventActionType,
    eventPage,
    setEventPage,
    totalEventPages,
    currentEventCount,
    eventLoading,
    eventError,
    setEventError,
    tradeEvents,
    cashEvents,
    corporateEvents,
    applyEventFilters,
    loadEventsPage,
    refreshPortfolioData,
    refreshPaperTradeSurfaces: refreshPaperTradeProjection,
    paperTradeProjectionRevision,
  } = usePortfolioProjectionSession({
    accountId: queryAccountId,
    costMethod,
    hasAccounts,
    language,
    riskFallbackMessage: text.riskFallback,
    loadAccounts,
    setError,
  });

  const mutation = usePortfolioLedgerMutationWorkflow({
    refreshPortfolioData,
    refreshPaperTradeSurfaces: refreshPaperTradeProjection,
  });
  const {
    tradeSubmitting,
    paperTradeSubmitting,
    paperTradeRefreshing,
    paperTradeRefreshIncomplete,
    cashSubmitting,
    corpSubmitting,
    csvCommitting,
    retryPaperTradeRefresh,
  } = mutation;

  const ledgerForms = usePortfolioLedgerEntryForms({
    language,
    text,
    writableAccountId,
    isPaperAccountSelected,
    setWriteWarning,
    mutation,
  });
  const {
    tradeModalOpen, setTradeModalOpen,
    paperTradeModalOpen, setPaperTradeModalOpen,
    cashModalOpen, setCashModalOpen,
    corpModalOpen, setCorpModalOpen,
    tradeError, setTradeError,
    paperTradeError, setPaperTradeError,
    paperTradeSuccess, setPaperTradeSuccess,
    cashError, setCashError,
    corpError, setCorpError,
    tradeForm, setTradeForm,
    paperTradeForm, setPaperTradeForm,
    cashForm, setCashForm,
    corpForm, setCorpForm,
    handleTradeSubmit,
    handlePaperTradeSubmit,
    handleCashSubmit,
    handleCorporateSubmit,
  } = ledgerForms;

  const csvSession = usePortfolioCsvImportSession({
    text,
    writableAccountId,
    setWriteWarning,
    commitCsv: mutation.commitCsv,
  });
  const {
    csvModalOpen, setCsvModalOpen,
    brokers, selectedBroker, setSelectedBroker,
    csvFile, setCsvFile,
    csvDryRun, setCsvDryRun,
    csvParsing, csvError, setCsvError,
    csvParseResult, setCsvParseResult,
    csvCommitResult, setCsvCommitResult,
    brokerLoadWarning, csvInputRef,
    loadBrokers, handleParseCsv, handleCommitCsv,
  } = csvSession;

  useEffect(() => {
    void loadAccounts();
    void loadBrokers();
  }, [loadAccounts, loadBrokers]);
  const paperTradeRefreshWarning = paperTradeRefreshIncomplete
    ? text.paperTradeRefreshWarning
    : null;
  const canDeleteSelectedAccount = (
    Boolean(writableAccountId)
    && !isLoading
    && !fxRefreshing
    && !accountDeleteLoading
  );

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
          accountType: accounts.find((item) => item.id === account.accountId)?.accountType ?? 'real',
        });
      }
    }
    rows.sort((a, b) => Number(b.marketValueBase || 0) - Number(a.marketValueBase || 0));
    return rows;
  }, [accounts, snapshot]);

  const snapshotMatchesAccountScope = useMemo(() => {
    if (!snapshot) return false;
    const snapshotAccountIds = new Set((snapshot.accounts || []).map((account) => account.accountId));
    if (queryAccountId !== undefined) {
      return snapshotAccountIds.size === 1 && snapshotAccountIds.has(queryAccountId);
    }
    return accounts.length === 0 || Number(snapshot.accountCount || 0) === accounts.length;
  }, [accounts.length, queryAccountId, snapshot]);

  const {
    portfolioSignalsLoading,
    portfolioSignalsWarning,
    signalByPositionKey,
    bumpSignalsRefresh,
  } = usePortfolioHoldingSignals({
    positionRows,
    snapshotMatchesAccountScope,
    paperTradeProjectionRevision,
    t,
  });

  const handleAnalyzePosition = async (row: FlatPosition) => {
    const key = `${row.accountId}-${row.symbol}-${row.market}`;
    setPositionAnalysisLoadingKey(key);
    setError(null);
    try {
      const task = await portfolioApi.analyzePosition(row.symbol, {
        accountId: row.accountId,
        analysisPhase: positionAnalysisPhase,
        force: false,
      });
      acceptPortfolioAnalysisTask(task, row.symbol, positionAnalysisPhase);
    } catch (err) {
      const parsed = getParsedApiError(err);
      const existingTaskId = String(
        parsed.params?.existing_task_id
          ?? parsed.params?.existingTaskId
          ?? '',
      ).trim();
      // Reattach an in-flight duplicate instead of leaving the user with only an error toast.
      if (parsed.code === 'duplicate_task' && existingTaskId) {
        await attachPortfolioAnalysisTask(existingTaskId, row.symbol, positionAnalysisPhase);
      } else {
        setError(parsed);
      }
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
      setSelectedAccount(nextAccount?.id ?? 'all', true);
      setPendingAccountDelete(null);
      setAccountDeleteError(null);
      setShowCreateAccount(false);
      setEditingAccountId(null);
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
        accountType: accountForm.accountType,
      });
      await loadAccounts();
      setSelectedAccount(created.id, true);
      setShowCreateAccount(false);
      setWriteWarning(null);
      setAccountForm({
        name: '',
        broker: 'Demo',
        market: accountForm.market,
        baseCurrency: accountForm.baseCurrency,
        accountType: 'real',
      });
      setAccountCreateSuccess(text.accountCreated);
    } catch (err) {
      setAccountCreateError(getParsedApiError(err, language).message || text.accountCreateFailed);
      setAccountCreateSuccess(null);
    } finally {
      setAccountCreating(false);
    }
  };

  const handleEditAccountOpen = (account: PortfolioAccountItem) => {
    setEditingAccountId(account.id);
    setAccountForm({
      name: account.name,
      broker: account.broker ?? '',
      market: account.market,
      baseCurrency: account.baseCurrency,
      accountType: account.accountType ?? 'real',
    });
    setAccountCreateError(null);
    setAccountCreateSuccess(null);
    setShowCreateAccount(true);
  };

  const handleUpdateAccount = async () => {
    if (editingAccountId == null) return;
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
      // PUT is a true update that preserves the account id, ledger, holdings,
      // and idempotency links (no delete + recreate).
      const updated = await portfolioApi.updateAccount(editingAccountId, {
        name,
        broker: accountForm.broker.trim(),
        market: accountForm.market,
        baseCurrency: accountForm.baseCurrency.trim() || 'CNY',
      });
      await loadAccounts();
      setSelectedAccount(updated.id, true);
      setShowCreateAccount(false);
      setEditingAccountId(null);
      setAccountCreateSuccess(text.accountUpdated);
    } catch (err) {
      setAccountCreateError(getParsedApiError(err, language).message || text.accountUpdateFailed);
      setAccountCreateSuccess(null);
    } finally {
      setAccountCreating(false);
    }
  };

  const handleAccountSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingAccountId != null) void handleUpdateAccount();
    else void handleCreateAccount(e);
  };

  const handleRefresh = async () => {
    await Promise.all([
      loadAccounts(),
      loadSnapshotAndRisk(),
      loadEventsPage(eventPage),
      loadBrokers(),
    ]);
    bumpSignalsRefresh();
  };

  const decisionSignalRiskPreviewItems = (risk?.decisionSignalRisk?.items ?? []).slice(0, 3);
  const formatDecisionSignalRiskAction = (
    signal: Pick<DecisionSignalItem, 'action'> & Partial<DecisionSignalItem>,
  ): string => getDecisionSignalPresentation(signal, decisionActionLabels).label;
  const snapshotQualityMessage = snapshot?.dataQuality === 'partial' && snapshot.limitations?.length
    ? snapshot.limitations
      .map((limitation) => formatPortfolioLimitation(limitation, language))
      .join(getUiClauseSeparator(language))
    : null;

  const positionColumns: DataTableColumn<FlatPosition>[] = [
    {
      id: 'account',
      header: text.account,
      cell: (row) => (
        <span className="flex flex-wrap items-center gap-1.5 text-secondary">
          <span>{row.accountName}</span>
          {row.accountType === 'paper' ? (
            <Badge variant="info">{text.paperAccount}</Badge>
          ) : null}
        </span>
      ),
    },
    {
      id: 'code',
      header: text.code,
      cell: (row) => <span className="font-mono text-foreground">{row.symbol}</span>,
    },
    {
      id: 'quantity',
      header: text.quantity,
      align: 'end',
      cell: (row) => <span className="text-foreground">{row.quantity.toFixed(2)}</span>,
    },
    {
      id: 'avgCost',
      header: text.avgCost,
      align: 'end',
      cell: (row) => <span className="text-foreground">{row.avgCost.toFixed(4)}</span>,
    },
    {
      id: 'lastPrice',
      header: text.lastPrice,
      align: 'end',
      cell: (row) => (
        <div className="text-foreground">
          <div>{formatPositionPrice(row)}</div>
          <div className={`text-xs ${hasPositionPrice(row) ? 'text-secondary' : 'text-warning'}`}>
            {getPositionPriceLabel(row, language)}
          </div>
        </div>
      ),
    },
    {
      id: 'marketValue',
      header: text.marketValue,
      align: 'end',
      cell: (row) => <span className="text-foreground">{formatPositionMoney(row.marketValueBase, row, language)}</span>,
    },
    {
      id: 'unrealizedPnl',
      header: text.unrealizedPnl,
      align: 'end',
      cell: (row) => (
        <span className={
          hasPositionPrice(row)
            ? row.unrealizedPnlBase >= 0 ? 'text-success' : 'text-danger'
            : 'text-secondary'
        }>
          {formatPositionMoney(row.unrealizedPnlBase, row, language)}
        </span>
      ),
    },
    {
      id: 'returnPct',
      header: text.returnPct,
      align: 'end',
      cell: (row) => (
        <span className={
          hasPositionPrice(row) && row.unrealizedPnlPct !== null && row.unrealizedPnlPct !== undefined
            ? row.unrealizedPnlPct >= 0 ? 'text-success' : 'text-danger'
            : 'text-secondary'
        }>
          {formatSignedPct(row.unrealizedPnlPct)}
        </span>
      ),
    },
    {
      id: 'signal',
      header: t('decisionSignals.portfolioColumn'),
      align: 'end',
      width: 'default',
      cell: (row) => {
        const signal = signalByPositionKey.get(`${row.accountId}-${row.symbol}-${row.market}`);
        return (
          <div className="flex min-w-44 flex-col items-end gap-1.5">
            <PortfolioSignalSummary
              item={signal}
              loading={portfolioSignalsLoading}
            />
            {signal ? (
              <Link
                to={buildSignalCenterHref({
                  tab: SIGNAL_CENTER_TAB_VALUES.rules,
                  createRule: true,
                  stock: row.symbol,
                })}
                data-control="navigation-link"
                className="control-hit-target inline-flex min-h-7 items-center px-1.5 text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
              >
                {t('decisionSignals.createRuleFromSignal')}
              </Link>
            ) : null}
          </div>
        );
      },
    },
    {
      id: 'action',
      header: text.action,
      align: 'end',
      cell: (row) => {
        const analyzing = positionAnalysisLoadingKey === `${row.accountId}-${row.symbol}-${row.market}`;
        return (
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
        );
      },
    },
  ];

  return (
    <AppPage className="portfolio-page space-y-4">
      <section className="space-y-3">
        <PageHeader
          title={text.title}
          description={text.description}
          actions={(
            <div
              data-portfolio-switcher="single"
              className="inline-flex min-h-9 items-center gap-2 text-sm font-medium text-foreground"
            >
              <BriefcaseBusiness className="h-4 w-4" aria-hidden="true" />
              <span>{t('layout.nav.portfolio')}</span>
              {isPaperAccountSelected ? (
                <Badge variant="info">{text.paperAccount}</Badge>
              ) : null}
            </div>
          )}
        />
      </section>

      {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}
      {accountCreateSuccess ? (
        <InlineAlert variant="success" size="compact" message={accountCreateSuccess} />
      ) : null}
      {paperTradeSuccess ? (
        <InlineAlert
          variant="success"
          size="compact"
          title={text.paperTradeSuccessTitle}
          message={paperTradeSuccess}
        />
      ) : null}
      {paperTradeRefreshWarning ? (
        <InlineAlert
          variant="warning"
          title={text.paperTradeRefreshWarningTitle}
          message={paperTradeRefreshWarning}
          action={(
            <Button
              type="button"
              variant="secondary"
              size="compact"
              onClick={() => void retryPaperTradeRefresh()}
              isLoading={paperTradeRefreshing}
              loadingText={text.refreshing}
            >
              {text.retryPaperTradeRefresh}
            </Button>
          )}
        />
      ) : null}
      {unavailableAccountId !== null ? (
        <InlineAlert
          variant="warning"
          title={t('deepLink.invalidTitle')}
          message={t('deepLink.invalidMessage')}
        />
      ) : null}
      {hasAccounts && riskWarning ? (
        <InlineAlert
          variant="warning"
          title={text.riskDegraded}
          message={riskWarning}
        />
      ) : null}
      {hasAccounts && writeWarning ? (
        <InlineAlert
          variant="warning"
          title={text.operationHint}
          message={writeWarning}
        />
      ) : null}
      {hasAccounts && portfolioAnalysisTasks.length > 0 ? (
        <div className="space-y-2" data-testid="portfolio-analysis-task-panel">
          <TaskPanel
            tasks={portfolioAnalysisTasks}
            title={text.analysisTask}
            onOpenRunFlow={openPortfolioRunFlow}
            onDismiss={dismissPortfolioAnalysisTask}
          />
          {portfolioAnalysisTasks.some((task) => task.status === 'completed') ? (
            <div className="flex flex-wrap gap-2">
              {portfolioAnalysisTasks
                .filter((task) => task.status === 'completed')
                .map((task) => (
                  <Link
                    key={`result-${task.taskId}`}
                    to={buildAnalysisWorkbenchHref({
                      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
                      stock: task.stockCode,
                    })}
                    data-control="navigation-link"
                    className="control-hit-target inline-flex min-h-9 items-center rounded-md border border-subtle bg-surface px-3 text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
                  >
                    {t('analysisWorkbench.viewReport')}: {task.stockName || task.stockCode}
                  </Link>
                ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <Modal
        isOpen={portfolioRunFlowDialog.open}
        onClose={closePortfolioRunFlow}
        title={portfolioRunFlowDialog.open
          ? t('runFlow.taskDrawerTitle', { stock: portfolioRunFlowDialog.title })
          : t('taskPanel.title')}
        size="fullscreen"
      >
        {portfolioRunFlowDialog.open ? (
          <RunFlowPanel
            key={`portfolio-run-flow-${portfolioRunFlowDialog.source.type === 'task' ? portfolioRunFlowDialog.source.taskId : 'none'}`}
            source={portfolioRunFlowDialog.source}
            title={t('runFlow.taskDrawerTitle', { stock: portfolioRunFlowDialog.title })}
            onUnavailable={() => {
              closePortfolioRunFlow();
            }}
          />
        ) : null}
      </Modal>

      <Modal
        isOpen={showCreateAccount}
        onClose={() => {
          if (!accountCreating) {
            setShowCreateAccount(false);
            setEditingAccountId(null);
          }
        }}
        title={editingAccountId != null ? text.editAccount : text.newAccount}
      >
          {!hasAccounts ? (
            <p className="mb-3 text-xs text-secondary">{text.createAutoSwitch}</p>
          ) : null}
          {accountCreateError ? (
            <InlineAlert
              variant="danger"
              size="compact"
              className="mt-2"
              title={text.createFailed}
              message={accountCreateError}
            />
          ) : null}
          <form className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2" onSubmit={handleAccountSubmit}>
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
            {editingAccountId == null ? (
              <div className="md:col-span-2">
                <Select
                  label={text.accountType}
                  value={accountForm.accountType}
                  onChange={(value) => setAccountForm((prev) => ({
                    ...prev,
                    accountType: value as PortfolioAccountType,
                  }))}
                  options={[
                    { value: 'real', label: text.realAccount },
                    { value: 'paper', label: text.paperAccount },
                  ]}
                  className="w-full"
                  triggerClassName="w-full"
                />
                <p className="mt-1.5 text-xs text-secondary-text">
                  {accountForm.accountType === 'paper'
                    ? text.paperAccountCreateHint
                    : text.realAccountCreateHint}
                </p>
              </div>
            ) : (
              <div className="md:col-span-2">
                <p className="mb-1.5 text-xs font-medium text-secondary-text">{text.accountType}</p>
                <Badge variant={accountForm.accountType === 'paper' ? 'info' : 'default'}>
                  {accountForm.accountType === 'paper' ? text.paperAccount : text.realAccount}
                </Badge>
                <p className="mt-1.5 text-xs text-secondary-text">{text.accountTypeLocked}</p>
              </div>
            )}
            <Button
              type="submit"
              variant="secondary"
              size="comfortable"
              className="md:col-span-2"
              isLoading={accountCreating}
              loadingText={editingAccountId != null ? text.savingAccount : text.creatingAccount}
            >
              {editingAccountId != null ? text.saveAccount : text.createAccount}
            </Button>
          </form>
      </Modal>

      {!accountsLoaded ? (
        <Loading label={text.loading} className="min-h-40" />
      ) : !hasAccounts ? (
        <EmptyState
          title={text.noAccounts}
          icon={<Inbox className="h-6 w-6" aria-hidden="true" />}
          action={(
            <Button
              type="button"
              variant="primary"
              onClick={() => {
                setEditingAccountId(null);
                setAccountForm({
                  name: '',
                  broker: 'Demo',
                  market: accountForm.market,
                  baseCurrency: accountForm.baseCurrency,
                  accountType: 'real',
                });
                setShowCreateAccount(true);
                setAccountCreateError(null);
                setAccountCreateSuccess(null);
              }}
            >
              {text.addAccount}
            </Button>
          )}
          className="min-h-40"
        />
      ) : (
        <>
      {snapshotQualityMessage ? (
        <InlineAlert
          variant="warning"
          size="compact"
          title={text.snapshotPartialTitle}
          message={snapshotQualityMessage}
        />
      ) : null}

      <section className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div className="space-y-3 xl:col-span-2">
          <Surface level="interactive" padding="sm">
              <div className="grid grid-cols-1 items-end gap-2 xl:grid-cols-[minmax(0,1fr)_220px_minmax(280px,1fr)]">
                <Select
                  label={text.accountView}
                  value={String(selectedAccount)}
                  onChange={(value) => setSelectedAccount(value === 'all' ? 'all' : Number(value))}
                  disabled={paperTradeSubmitting || paperTradeRefreshing}
                  options={[
                    { value: 'all', label: text.allAccounts },
                    ...accounts.map((account) => ({
                      value: String(account.id),
                      label: `${account.name} (#${account.id})${
                        (account.accountType ?? 'real') === 'paper'
                          ? ` · ${text.paperAccount}`
                          : ''
                      }`,
                    })),
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
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="comfortable"
                    className="whitespace-nowrap"
                    onClick={() => {
                      setEditingAccountId(null);
                      setAccountForm({
                        name: '',
                        broker: 'Demo',
                        market: accountForm.market,
                        baseCurrency: accountForm.baseCurrency,
                        accountType: 'real',
                      });
                      setShowCreateAccount(true);
                      setAccountCreateError(null);
                      setAccountCreateSuccess(null);
                    }}
                  >
                    {text.createAccount}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="comfortable"
                    className="whitespace-nowrap"
                    disabled={!writableAccount || isLoading || fxRefreshing}
                    onClick={() => {
                      if (writableAccount) handleEditAccountOpen(writableAccount);
                    }}
                  >
                    {text.editAccount}
                  </Button>
                  <Button
                    type="button"
                    onClick={() => void handleRefresh()}
                    disabled={isLoading || fxRefreshing}
                    variant="secondary"
                    size="comfortable"
                    isLoading={isLoading}
                    loadingText={text.refreshing}
                    className="whitespace-nowrap"
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
                    className="whitespace-nowrap"
                  >
                    {text.deleteAccount}
                  </Button>
                </div>
              </div>
          </Surface>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Card variant="gradient" padding="md">
              <p className="text-sm text-secondary">{text.totalEquity}</p>
              <p className="mt-1 text-2xl font-semibold text-foreground">{formatMoney(snapshot?.totalEquity, snapshot?.currency || 'CNY', language)}</p>
            </Card>
            <Card variant="gradient" padding="md">
              <p className="text-sm text-secondary">{text.totalMarketValue}</p>
              <p className="mt-1 text-2xl font-semibold text-foreground">{formatMoney(snapshot?.totalMarketValue, snapshot?.currency || 'CNY', language)}</p>
            </Card>
            <Card variant="gradient" padding="md">
              <p className="text-sm text-secondary">{text.totalCash}</p>
              <p className="mt-1 text-2xl font-semibold text-foreground">{formatMoney(snapshot?.totalCash, snapshot?.currency || 'CNY', language)}</p>
            </Card>
            <Card variant="gradient" padding="md">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm text-secondary">{text.fxStatus}</p>
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
                  size="compact"
                  title={text.fxRefreshResult}
                  message={fxRefreshFeedback.text}
                  className="mt-3"
                />
              ) : null}
            </Card>
          </div>
        </div>

        <Card padding="md" className="xl:col-start-3 xl:row-start-1">
          <h2 className="mb-3 text-sm font-semibold text-foreground">
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
              compact
            />
          )}
          <div className="mt-3 space-y-1 text-xs text-secondary">
            <div>{text.displayScope}: {concentrationMode === 'sector' ? text.sectorDimension : text.positionDimensionFallback}</div>
            <div>{text.sectorAlert}: {risk?.sectorConcentration?.alert ? text.yes : text.no}</div>
            <div>{text.topWeight}: {formatPct(risk?.sectorConcentration?.topWeightPct ?? risk?.concentration?.topWeightPct)}</div>
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-3">
        <Card padding="md">
          <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-foreground">{text.positionsTitle}</h2>
              <span className="mt-1 block text-xs text-secondary">
                {formatUiText(text.countItems, { count: positionRows.length })}
              </span>
            </div>
            <AnalysisPhaseSelect
              id="portfolio-analysis-phase"
              value={positionAnalysisPhase}
              onChange={setPositionAnalysisPhase}
              label={t('analysis.phase')}
              hint={t('analysis.phaseHint')}
              disabled={positionAnalysisLoadingKey !== null}
              className="w-full sm:w-64"
            />
          </div>
          {portfolioSignalsWarning ? (
            <InlineAlert
              variant="warning"
              size="compact"
              title={t('decisionSignals.portfolioWarningTitle')}
              message={portfolioSignalsWarning}
              className="mb-3"
            />
          ) : null}
          <DataTable<FlatPosition>
            caption={text.positionsTitle}
            columns={positionColumns}
            rows={positionRows}
            getRowKey={(row) => `${row.accountId}-${row.symbol}-${row.market}`}
            emptyState={{
              title: text.noPositionsTitle,
              description: text.noPositionsDescription,
            }}
            density="compact"
            minWidth="wide"
          />
        </Card>
      </section>

      {writeBlocked && hasAccounts ? (
        <InlineAlert
          variant="warning"
          size="compact"
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
            <Link
              to={buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.holdings })}
              data-control="navigation-link"
              className="control-hit-target mt-2 inline-flex min-h-7 items-center text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
            >
              {t('decisionSignals.viewAll')}
            </Link>
          </div>
        </Card>
      </section>

      <div className="flex flex-wrap gap-2">
        {isPaperAccountSelected ? (
          <Button
            type="button"
            variant="primary"
            size="comfortable"
            onClick={() => {
              setPaperTradeError(null);
              setPaperTradeSuccess(null);
              setPaperTradeModalOpen(true);
            }}
            disabled={!writableAccountId || paperTradeSubmitting || paperTradeRefreshing}
          >
            {text.enterPaperTrade}
          </Button>
        ) : (
          <Button type="button" variant="secondary" size="comfortable" onClick={() => setTradeModalOpen(true)} disabled={!writableAccountId}>{text.enterTrade}</Button>
        )}
        <Button type="button" variant="secondary" size="comfortable" onClick={() => setCashModalOpen(true)} disabled={!writableAccountId}>{text.enterCash}</Button>
        <Button type="button" variant="secondary" size="comfortable" onClick={() => setCorpModalOpen(true)} disabled={!writableAccountId}>{text.enterCorporate}</Button>
        <Button type="button" variant="secondary" size="comfortable" className="text-xs" onClick={() => setCsvModalOpen(true)}>{text.csvImport}</Button>
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
            <div className="grid grid-cols-1">
              <Button type="submit" variant="secondary" size="comfortable" disabled={!writableAccountId} isLoading={tradeSubmitting} loadingText={text.submitting}>
                {text.submitTrade}
              </Button>
            </div>
            </fieldset>
          </form>
      </Modal>

      <Modal
        isOpen={paperTradeModalOpen}
        closeDisabled={paperTradeSubmitting}
        onClose={() => {
          setPaperTradeError(null);
          setPaperTradeModalOpen(false);
        }}
        title={text.enterPaperTrade}
      >
        <form onSubmit={handlePaperTradeSubmit} aria-busy={paperTradeSubmitting}>
          <fieldset disabled={paperTradeSubmitting} className="m-0 min-w-0 space-y-2 border-0 p-0">
            <InlineAlert
              variant="info"
              size="compact"
              title={text.paperAccount}
              message={text.paperTradeSimulationHint}
            />
            <Input
              id="portfolio-paper-trade-symbol"
              label={text.stockCode}
              placeholder={text.stockExample}
              value={paperTradeForm.symbol}
              onChange={(event) => setPaperTradeForm((current) => ({
                ...current,
                symbol: event.target.value,
              }))}
              required
            />
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <DatePicker
                label={text.tradeDate}
                value={paperTradeForm.tradeDate}
                onChange={(tradeDate) => setPaperTradeForm((current) => ({
                  ...current,
                  tradeDate,
                }))}
                required
                className="w-full"
                triggerClassName={PORTFOLIO_DATE_TRIGGER_CLASS}
              />
              <Select
                label={text.side}
                value={paperTradeForm.side}
                disabled={paperTradeSubmitting}
                onChange={(value) => setPaperTradeForm((current) => ({
                  ...current,
                  side: value as PortfolioSide,
                }))}
                options={[
                  { value: 'buy', label: text.buy },
                  { value: 'sell', label: text.sell },
                ]}
              />
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Input
                id="portfolio-paper-trade-quantity"
                label={text.quantity}
                type="number"
                min="0.0001"
                step="0.0001"
                placeholder={text.required}
                value={paperTradeForm.quantity}
                onChange={(event) => setPaperTradeForm((current) => ({
                  ...current,
                  quantity: event.target.value,
                }))}
                required
              />
              <Input
                id="portfolio-paper-trade-price"
                label={text.tradePrice}
                type="number"
                min="0.0001"
                step="0.0001"
                placeholder={text.optional}
                value={paperTradeForm.price}
                onChange={(event) => setPaperTradeForm((current) => ({
                  ...current,
                  price: event.target.value,
                }))}
              />
            </div>
            <p className="text-xs text-secondary-text">{text.paperPriceHint}</p>
            <Input
              label={text.note}
              placeholder={text.optional}
              maxLength={255}
              value={paperTradeForm.note}
              onChange={(event) => setPaperTradeForm((current) => ({
                ...current,
                note: event.target.value,
              }))}
            />
            {paperTradeError ? (
              <ApiErrorAlert
                error={paperTradeError}
                onDismiss={() => setPaperTradeError(null)}
              />
            ) : null}
            <Button
              type="submit"
              variant="primary"
              size="comfortable"
              disabled={!isPaperAccountSelected}
              isLoading={paperTradeSubmitting}
              loadingText={text.submitting}
            >
              {text.enterPaperTrade}
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
            <div className="grid grid-cols-1">
              <Button type="submit" variant="secondary" size="comfortable" disabled={!writableAccountId} isLoading={cashSubmitting} loadingText={text.submitting}>
                {text.submitCash}
              </Button>
            </div>
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
            <div className="grid grid-cols-1">
              <Button type="submit" variant="secondary" size="comfortable" disabled={!writableAccountId} isLoading={corpSubmitting} loadingText={text.submitting}>
                {text.submitCorporate}
              </Button>
            </div>
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
                size="compact"
                message={brokerLoadWarning}
              />
            ) : null}
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Select
                label={text.broker}
                value={selectedBroker}
                onChange={(value) => {
                  setSelectedBroker(value);
                  setCsvCommitResult(null);
                }}
                disabled={csvParsing || csvCommitting || brokers.length === 0}
                options={brokers.map((item) => ({ value: item.broker, label: formatBrokerLabel(item.broker, item.displayName, language) }))}
              />
              <div className="grid gap-1">
                <span className="block text-xs text-muted-text">{text.csvFile}</span>
                <Button
                  type="button"
                  variant="secondary"
                  size="primary"
                  disabled={csvParsing || csvCommitting || brokers.length === 0}
                  onClick={() => csvInputRef.current?.click()}
                >
                  {text.chooseCsv}
                </Button>
                <FileInput
                  ref={csvInputRef}
                  accept=".csv"
                  aria-label={text.chooseCsv}
                  disabled={csvParsing || csvCommitting || brokers.length === 0}
                  onChange={(e) => {
                    setCsvFile(e.target.files && e.target.files[0] ? e.target.files[0] : null);
                    setCsvParseResult(null);
                    setCsvCommitResult(null);
                  }}
                />
                {csvFile ? (
                  <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-subtle-soft px-2 py-1.5">
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
              }}
              containerClassName="min-h-11 text-xs text-secondary"
              label={<span className="text-xs font-normal text-secondary-text">{text.dryRun}</span>}
            />
            <div className="grid grid-cols-2 gap-2">
              <Button type="button" variant="secondary" size="comfortable" disabled={!selectedBroker || !csvFile || csvCommitting} isLoading={csvParsing} loadingText={text.parsing} onClick={() => void handleParseCsv()}>
                {text.parseFile}
              </Button>
              <Button type="button" variant="secondary" size="comfortable"
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
                size="compact"
                title={text.csvParseResult}
                message={formatUiText(text.csvParseSummary, { valid: csvParseResult.recordCount, skipped: csvParseResult.skippedCount, errors: csvParseResult.errorCount })}
              />
            ) : null}
            {csvCommitResult ? (
              <InlineAlert
                variant={getCsvCommitVariant(csvCommitResult, csvCommitResult.dryRun)}
                size="compact"
                title={csvCommitResult.dryRun ? text.csvDryResult : text.csvCommitResult}
                message={formatUiText(text.csvCommitSummary, { mode: csvCommitResult.dryRun ? text.dryCheck : text.actualWrite, inserted: csvCommitResult.insertedCount, duplicates: csvCommitResult.duplicateCount, failed: csvCommitResult.failedCount })}
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
                onChange={(value) => setEventType(value as PortfolioEventType)}
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
            <div className="max-h-64 overflow-auto rounded-lg border border-subtle p-2">
              {eventType === 'trade' && tradeEvents.map((item) => (
                <div key={`t-${item.id}`} className="flex items-start justify-between gap-3 border-b border-subtle py-2 text-xs text-secondary">
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
                <div key={`c-${item.id}`} className="flex items-start justify-between gap-3 border-b border-subtle py-2 text-xs text-secondary">
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
                <div key={`ca-${item.id}`} className="flex items-start justify-between gap-3 border-b border-subtle py-2 text-xs text-secondary">
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
                      compact
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
        </>
      )}
    </AppPage>
  );
};

export default PortfolioWorkspace;
