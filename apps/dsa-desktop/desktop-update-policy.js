// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

'use strict';

const LOCAL_ONLY_STATUS_PATH = '/api/v1/security/local-only';

const UPDATE_CHECK_DECISION = Object.freeze({
  ALLOW: 'allow',
  SKIP_LOCAL_ONLY: 'skip-local-only',
  SKIP_UNKNOWN: 'skip-unknown',
});

const SKIP_LOCAL_ONLY_MESSAGE =
  'Desktop update checks are skipped because Local Only Mode is enabled. GitHub Releases is a non-loopback destination.';
const SKIP_UNKNOWN_MESSAGE =
  'Desktop update checks are skipped because Local Only Mode status could not be confirmed. The desktop does not contact GitHub unless Local Only is confirmed off.';

function parseLocalOnlyModeStatus(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return { known: false, enabled: null };
  }
  if (payload.enabled === true) {
    return { known: true, enabled: true };
  }
  if (payload.enabled === false) {
    return { known: true, enabled: false };
  }
  return { known: false, enabled: null };
}

function decideDesktopUpdateCheckEligibility(status) {
  if (status && status.known === true && status.enabled === false) {
    return {
      allowed: true,
      decision: UPDATE_CHECK_DECISION.ALLOW,
      message: '',
    };
  }
  if (status && status.known === true && status.enabled === true) {
    return {
      allowed: false,
      decision: UPDATE_CHECK_DECISION.SKIP_LOCAL_ONLY,
      message: SKIP_LOCAL_ONLY_MESSAGE,
    };
  }
  return {
    allowed: false,
    decision: UPDATE_CHECK_DECISION.SKIP_UNKNOWN,
    message: SKIP_UNKNOWN_MESSAGE,
  };
}

function buildLocalOnlyStatusUrl(origin) {
  if (typeof origin !== 'string' || !origin.trim()) {
    return null;
  }
  try {
    const url = new URL(LOCAL_ONLY_STATUS_PATH, origin);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return null;
    }
    return url.toString();
  } catch (_error) {
    return null;
  }
}

module.exports = {
  LOCAL_ONLY_STATUS_PATH,
  SKIP_LOCAL_ONLY_MESSAGE,
  SKIP_UNKNOWN_MESSAGE,
  UPDATE_CHECK_DECISION,
  buildLocalOnlyStatusUrl,
  decideDesktopUpdateCheckEligibility,
  parseLocalOnlyModeStatus,
};
