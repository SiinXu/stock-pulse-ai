// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { markSessionRestoreSuppressed } from '../utils/sessionContinuity';
import {
  resolveLegacyRouteRedirect,
  type LegacyRouteRedirectOptions,
} from './legacyRouteRedirect';

type LegacyRouteRedirectProps = LegacyRouteRedirectOptions & {
  to: string;
};

export const LegacyRouteRedirect: React.FC<LegacyRouteRedirectProps> = ({
  to,
  mapSearchParams,
  overrideSearchParams,
}) => {
  const location = useLocation();
  return (
    <Navigate
      replace
      to={resolveLegacyRouteRedirect(location, to, {
        mapSearchParams,
        overrideSearchParams,
      })}
      state={markSessionRestoreSuppressed(location.state)}
    />
  );
};
