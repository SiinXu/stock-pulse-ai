// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Shared Portfolio page types for section components and feature hooks.

import type {
  PortfolioAccountType,
  PortfolioCashDirection,
  PortfolioCorporateActionType,
  PortfolioPositionItem,
  PortfolioSide,
} from '../../types/portfolio';
import type { PORTFOLIO_FILE_TEXT, PORTFOLIO_TEXT } from '../../locales/portfolio';
import type { UiLanguage } from '../../i18n/uiText';

export type AccountOption = 'all' | number;

export type FlatPosition = PortfolioPositionItem & {
  accountId: number;
  accountName: string;
  accountType: PortfolioAccountType;
};

export type PortfolioAccountMarket = 'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw';

export type PendingDelete =
  | { eventType: 'trade'; id: number; message: string }
  | { eventType: 'cash'; id: number; message: string }
  | { eventType: 'corporate'; id: number; message: string };

export type PendingAccountDelete = {
  accountId: number;
  accountName: string;
};

export type PortfolioText = (typeof PORTFOLIO_TEXT)[UiLanguage];
export type PortfolioFileText = (typeof PORTFOLIO_FILE_TEXT)[UiLanguage];

export type AccountFormState = {
  name: string;
  broker: string;
  market: PortfolioAccountMarket;
  baseCurrency: string;
  accountType: PortfolioAccountType;
};

export type TradeFormState = {
  symbol: string;
  tradeDate: string;
  side: PortfolioSide;
  quantity: string;
  price: string;
  fee: string;
  tax: string;
  tradeUid: string;
  note: string;
};

export type PaperTradeFormState = {
  symbol: string;
  tradeDate: string;
  side: PortfolioSide;
  quantity: string;
  price: string;
  note: string;
};

export type CashFormState = {
  eventDate: string;
  direction: PortfolioCashDirection;
  amount: string;
  currency: string;
  note: string;
};

export type CorporateFormState = {
  symbol: string;
  effectiveDate: string;
  actionType: PortfolioCorporateActionType;
  cashDividendPerShare: string;
  splitRatio: string;
  note: string;
};
