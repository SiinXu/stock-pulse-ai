export type ApprovalRiskSource = 'risk_veto' | 'risk_downgrade';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired' | 'cancelled';
export type ApprovalDecision = 'approved' | 'rejected' | 'cancelled';

export interface ApprovalContext {
  stockCode: string;
  originalSignal: 'buy' | 'hold' | 'sell';
  conservativeSignal: 'buy' | 'hold' | 'sell';
  riskSource: ApprovalRiskSource;
  riskSummary: string;
}

export interface ApprovalRule {
  owner: string;
  action: 'risk_control_bypass';
  enabled: boolean;
  riskSources: ApprovalRiskSource[];
  expiresInSeconds: number;
  version: number;
  updatedAt: string | null;
}

export interface ApprovalProposal {
  id: string;
  owner: string;
  status: ApprovalStatus;
  version: number;
  expiresAt: string;
  consumedAt: string | null;
  context: ApprovalContext;
}

export interface ApprovalProposalPage {
  items: ApprovalProposal[];
  page: number;
  pageSize: number;
  total: number;
}

export interface ApprovalRuleUpdate {
  enabled: boolean;
  riskSources: ApprovalRiskSource[];
  expiresInSeconds: number;
  expectedVersion: number;
}
