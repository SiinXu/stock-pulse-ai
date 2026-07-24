// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { markSessionRestoreSuppressed } from '../utils/sessionContinuity';
import { resolveLegacyHomeAnalysisRedirect } from './homeAnalysisRedirect';

type LegacyHomeAnalysisRedirectProps = {
  children: React.ReactNode;
};

export const LegacyHomeAnalysisRedirect: React.FC<LegacyHomeAnalysisRedirectProps> = ({ children }) => {
  const location = useLocation();
  const target = resolveLegacyHomeAnalysisRedirect(location);
  return target ? (
    <Navigate
      replace
      to={target}
      state={markSessionRestoreSuppressed(location.state)}
    />
  ) : children;
};
