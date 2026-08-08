// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { InvestmentFrameworkSettingsCard } from '..';

export type AgentBehaviorSectionProps = {
  isInvestmentFrameworkView: boolean;
};

export const AgentBehaviorSection: React.FC<AgentBehaviorSectionProps> = ({ isInvestmentFrameworkView }) => (
  isInvestmentFrameworkView ? <InvestmentFrameworkSettingsCard /> : null
);
