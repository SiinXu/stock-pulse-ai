// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Feature-private ledger entry form state for the Portfolio route.
// Mutation identity and operationId scoping stay in usePortfolioLedgerMutationWorkflow.

import { useEffect, useState, type FormEvent } from 'react';
import type { ParsedApiError } from '../../api/error';
import { createParsedApiError, getParsedApiError } from '../../api/error';
import type { UiLanguage } from '../../i18n/uiText';
import { formatUiText } from '../../i18n/uiText';
import type {
  PortfolioCashDirection,
  PortfolioCorporateActionType,
  PortfolioSide,
} from '../../types/portfolio';
import { getTodayIso } from '../../utils/portfolioFormat';
import type {
  CashFormState,
  CorporateFormState,
  PaperTradeFormState,
  PortfolioText,
  TradeFormState,
} from './types';
import type { usePortfolioLedgerMutationWorkflow } from './usePortfolioLedgerMutationWorkflow';

type MutationWorkflow = ReturnType<typeof usePortfolioLedgerMutationWorkflow>;

type UsePortfolioLedgerEntryFormsOptions = {
  language: UiLanguage;
  text: PortfolioText;
  writableAccountId: number | undefined;
  isPaperAccountSelected: boolean;
  setWriteWarning: (warning: string | null) => void;
  mutation: Pick<
    MutationWorkflow,
    | 'tradeSubmitting'
    | 'paperTradeSubmitting'
    | 'cashSubmitting'
    | 'corpSubmitting'
    | 'submitTrade'
    | 'submitPaperTrade'
    | 'submitCash'
    | 'submitCorporateAction'
  >;
};

export function usePortfolioLedgerEntryForms({
  language,
  text,
  writableAccountId,
  isPaperAccountSelected,
  setWriteWarning,
  mutation,
}: UsePortfolioLedgerEntryFormsOptions) {
  const {
    tradeSubmitting,
    paperTradeSubmitting,
    cashSubmitting,
    corpSubmitting,
    submitTrade,
    submitPaperTrade,
    submitCash,
    submitCorporateAction,
  } = mutation;

  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [paperTradeModalOpen, setPaperTradeModalOpen] = useState(false);
  const [cashModalOpen, setCashModalOpen] = useState(false);
  const [corpModalOpen, setCorpModalOpen] = useState(false);
  const [tradeError, setTradeError] = useState<ParsedApiError | null>(null);
  const [paperTradeError, setPaperTradeError] = useState<ParsedApiError | null>(null);
  const [paperTradeSuccess, setPaperTradeSuccess] = useState<string | null>(null);
  const [cashError, setCashError] = useState<ParsedApiError | null>(null);
  const [corpError, setCorpError] = useState<ParsedApiError | null>(null);

  const [tradeForm, setTradeForm] = useState<TradeFormState>({
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
  const [paperTradeForm, setPaperTradeForm] = useState<PaperTradeFormState>({
    symbol: '',
    tradeDate: getTodayIso(),
    side: 'buy' as PortfolioSide,
    quantity: '',
    price: '',
    note: '',
  });
  const [cashForm, setCashForm] = useState<CashFormState>({
    eventDate: getTodayIso(),
    direction: 'in' as PortfolioCashDirection,
    amount: '',
    currency: '',
    note: '',
  });
  const [corpForm, setCorpForm] = useState<CorporateFormState>({
    symbol: '',
    effectiveDate: getTodayIso(),
    actionType: 'cash_dividend' as PortfolioCorporateActionType,
    cashDividendPerShare: '',
    splitRatio: '',
    note: '',
  });

  useEffect(() => {
    if (!isPaperAccountSelected && !paperTradeSubmitting) {
      // Close paper-trade UI when the selected account is no longer paper.
      // Preserves the prior PortfolioPage effect contract.
      /* eslint-disable react-hooks/set-state-in-effect -- intentional account-type gate */
      setPaperTradeModalOpen(false);
      setPaperTradeError(null);
      /* eslint-enable react-hooks/set-state-in-effect */
    }
  }, [isPaperAccountSelected, paperTradeSubmitting]);

  const handleTradeSubmit = async (e: FormEvent) => {
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
    setTradeError(null);
    setWriteWarning(null);
    try {
      await submitTrade(requestPayload, () => {
        setTradeForm((prev) => ({ ...prev, symbol: '', tradeUid: '', note: '' }));
        setTradeModalOpen(false);
      });
    } catch (err) {
      setTradeError(getParsedApiError(err));
    }
  };

  const handlePaperTradeSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!writableAccountId || !isPaperAccountSelected) {
      setPaperTradeError(createParsedApiError({
        title: text.paperTradeFailed,
        message: text.paperAccountRequired,
        code: 'paper_account_required',
      }));
      return;
    }
    if (!paperTradeForm.symbol.trim()) {
      document.getElementById('portfolio-paper-trade-symbol')?.focus();
      return;
    }
    if (!Number.isFinite(Number(paperTradeForm.quantity)) || Number(paperTradeForm.quantity) <= 0) {
      document.getElementById('portfolio-paper-trade-quantity')?.focus();
      return;
    }
    const requestedPrice = paperTradeForm.price.trim();
    if (
      requestedPrice
      && (!Number.isFinite(Number(requestedPrice)) || Number(requestedPrice) <= 0)
    ) {
      document.getElementById('portfolio-paper-trade-price')?.focus();
      return;
    }
    if (paperTradeSubmitting) return;

    const requestPayload = {
      symbol: paperTradeForm.symbol.trim(),
      tradeDate: paperTradeForm.tradeDate,
      side: paperTradeForm.side,
      quantity: Number(paperTradeForm.quantity),
      price: requestedPrice ? Number(requestedPrice) : undefined,
      note: paperTradeForm.note.trim() || undefined,
    };
    setPaperTradeError(null);
    setPaperTradeSuccess(null);
    setWriteWarning(null);

    try {
      await submitPaperTrade(writableAccountId, requestPayload, (result) => {
        const priceSource = result.priceSource === 'latest_close'
          ? text.paperLatestClose
          : result.priceSource === 'manual'
            ? text.paperEnteredPrice
            : result.priceSource;
        setPaperTradeSuccess(formatUiText(text.paperTradeRecorded, {
          side: paperTradeForm.side === 'buy' ? text.buy : text.sell,
          symbol: requestPayload.symbol,
          quantity: requestPayload.quantity,
          price: result.price,
          source: priceSource,
        }));
        setPaperTradeForm((current) => ({
          ...current,
          symbol: '',
          quantity: '',
          price: '',
          note: '',
        }));
        setPaperTradeModalOpen(false);
      });
    } catch (err) {
      const parsed = getParsedApiError(err, language);
      const message = parsed.code === 'paper_account_required'
        ? text.paperAccountRequired
        : parsed.code === 'insufficient_cash'
          ? text.paperInsufficientCash
          : parsed.code === 'quote_unavailable'
            ? text.paperQuoteUnavailable
            : null;
      setPaperTradeError(message
        ? { ...parsed, title: text.paperTradeFailed, message }
        : parsed);
    }
  };

  const handleCashSubmit = async (e: FormEvent) => {
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
    setCashError(null);
    setWriteWarning(null);
    try {
      await submitCash(requestPayload, () => {
        setCashForm((prev) => ({ ...prev, note: '' }));
        setCashModalOpen(false);
      });
    } catch (err) {
      setCashError(getParsedApiError(err));
    }
  };

  const handleCorporateSubmit = async (e: FormEvent) => {
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
    setCorpError(null);
    setWriteWarning(null);
    try {
      await submitCorporateAction(requestPayload, () => {
        setCorpForm((prev) => ({ ...prev, symbol: '', note: '' }));
        setCorpModalOpen(false);
      });
    } catch (err) {
      setCorpError(getParsedApiError(err));
    }
  };

  return {
    tradeModalOpen,
    setTradeModalOpen,
    paperTradeModalOpen,
    setPaperTradeModalOpen,
    cashModalOpen,
    setCashModalOpen,
    corpModalOpen,
    setCorpModalOpen,
    tradeError,
    setTradeError,
    paperTradeError,
    setPaperTradeError,
    paperTradeSuccess,
    setPaperTradeSuccess,
    cashError,
    setCashError,
    corpError,
    setCorpError,
    tradeForm,
    setTradeForm,
    paperTradeForm,
    setPaperTradeForm,
    cashForm,
    setCashForm,
    corpForm,
    setCorpForm,
    handleTradeSubmit,
    handlePaperTradeSubmit,
    handleCashSubmit,
    handleCorporateSubmit,
  };
}
