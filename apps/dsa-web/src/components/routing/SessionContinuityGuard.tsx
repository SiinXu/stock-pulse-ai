// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import {
  isSessionRestoreSuppressed,
  recordSessionLocation,
  resolveInitialSessionHref,
} from '../../utils/sessionContinuity';

type SessionContinuityGuardProps = {
  children: React.ReactNode;
};

export const SessionContinuityGuard: React.FC<SessionContinuityGuardProps> = ({ children }) => {
  const location = useLocation();
  const currentHref = `${location.pathname}${location.search}${location.hash}`;
  const [{ initialLocationKey, initialRestore }] = useState(() => ({
    initialLocationKey: location.key,
    initialRestore: isSessionRestoreSuppressed(location.state)
      ? null
      : resolveInitialSessionHref(currentHref),
  }));
  const restorePending = Boolean(
    initialRestore
    && location.key === initialLocationKey
    && initialRestore !== currentHref,
  );

  useEffect(() => {
    if (restorePending) return;
    recordSessionLocation(currentHref);
  }, [currentHref, restorePending]);

  return restorePending && initialRestore
    ? <Navigate to={initialRestore} replace state={location.state} />
    : children;
};
