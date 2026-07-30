// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Domain content for the local personal investment framework. */
export interface InvestmentFrameworkContent {
  [key: string]: unknown;
  schemaVersion?: 'investment-framework-content-v1';
  title: string;
  description?: string | null;
  rootNodeId?: string | null;
  decisionTree?: InvestmentFrameworkDecisionNode[];
  evaluationDimensions?: InvestmentFrameworkEvaluationDimension[];
  riskRules?: string[];
  trackingCriteria?: string[];
  freeFormRules?: string | null;
}

export interface InvestmentFrameworkDecisionBranch {
  [key: string]: unknown;
  condition: string;
  targetNodeId?: string | null;
  outcome?: string | null;
}

export interface InvestmentFrameworkDecisionNode {
  [key: string]: unknown;
  nodeId: string;
  question: string;
  branches: InvestmentFrameworkDecisionBranch[];
}

export interface InvestmentFrameworkEvaluationDimension {
  [key: string]: unknown;
  name: string;
  weight: number;
  criteria?: string[];
  description?: string | null;
}

export interface InvestmentFrameworkResponse {
  frameworkId: number;
  scope: 'local';
  version: number;
  activeVersion: number | null;
  revision: number;
  isActive: boolean;
  content: InvestmentFrameworkContent;
  changeSummary?: string | null;
  createdAt: string;
  updatedAt: string;
  versionCreatedAt: string;
}

export interface InvestmentFrameworkCreateRequest {
  content: InvestmentFrameworkContent;
  changeSummary?: string | null;
}

export interface InvestmentFrameworkUpdateRequest {
  expectedRevision: number;
  content: InvestmentFrameworkContent;
  changeSummary?: string | null;
}

export interface InvestmentFrameworkDeactivateRequest {
  expectedRevision: number;
}

export interface InvestmentFrameworkDeleteResponse {
  deleted: true;
  frameworkId: number;
  deletedThroughVersion: number;
}

export interface InvestmentFrameworkHistoryItem {
  version: number;
  isActive: boolean;
  content: InvestmentFrameworkContent;
  changeSummary?: string | null;
  createdAt: string;
}

export interface InvestmentFrameworkHistoryResponse {
  frameworkId: number;
  latestVersion: number;
  activeVersion: number | null;
  revision: number;
  items: InvestmentFrameworkHistoryItem[];
  total: number;
}
