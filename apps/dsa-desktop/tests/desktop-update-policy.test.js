// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  LOCAL_ONLY_STATUS_PATH,
  SKIP_LOCAL_ONLY_MESSAGE,
  SKIP_UNKNOWN_MESSAGE,
  UPDATE_CHECK_DECISION,
  buildLocalOnlyStatusUrl,
  decideDesktopUpdateCheckEligibility,
  parseLocalOnlyModeStatus,
} = require('../desktop-update-policy');

test('parseLocalOnlyModeStatus treats only boolean enabled as known', () => {
  assert.deepEqual(parseLocalOnlyModeStatus({ enabled: true }), { known: true, enabled: true });
  assert.deepEqual(parseLocalOnlyModeStatus({ enabled: false }), { known: true, enabled: false });
  assert.deepEqual(parseLocalOnlyModeStatus({ enabled: 'true' }), { known: false, enabled: null });
  assert.deepEqual(parseLocalOnlyModeStatus({ enabled: 0 }), { known: false, enabled: null });
  assert.deepEqual(parseLocalOnlyModeStatus({}), { known: false, enabled: null });
  assert.deepEqual(parseLocalOnlyModeStatus(null), { known: false, enabled: null });
  assert.deepEqual(parseLocalOnlyModeStatus(undefined), { known: false, enabled: null });
  assert.deepEqual(parseLocalOnlyModeStatus(['enabled']), { known: false, enabled: null });
});

test('decideDesktopUpdateCheckEligibility allows only confirmed Local Only off', () => {
  assert.deepEqual(
    decideDesktopUpdateCheckEligibility({ known: true, enabled: false }),
    {
      allowed: true,
      decision: UPDATE_CHECK_DECISION.ALLOW,
      message: '',
    }
  );
});

test('decideDesktopUpdateCheckEligibility skips when Local Only is on', () => {
  assert.deepEqual(
    decideDesktopUpdateCheckEligibility({ known: true, enabled: true }),
    {
      allowed: false,
      decision: UPDATE_CHECK_DECISION.SKIP_LOCAL_ONLY,
      message: SKIP_LOCAL_ONLY_MESSAGE,
    }
  );
});

test('decideDesktopUpdateCheckEligibility fail-closes when status is unknown', () => {
  const unknown = {
    allowed: false,
    decision: UPDATE_CHECK_DECISION.SKIP_UNKNOWN,
    message: SKIP_UNKNOWN_MESSAGE,
  };
  assert.deepEqual(decideDesktopUpdateCheckEligibility({ known: false, enabled: null }), unknown);
  assert.deepEqual(decideDesktopUpdateCheckEligibility({ known: true, enabled: null }), unknown);
  assert.deepEqual(decideDesktopUpdateCheckEligibility(null), unknown);
  assert.deepEqual(decideDesktopUpdateCheckEligibility(undefined), unknown);
  assert.deepEqual(decideDesktopUpdateCheckEligibility({}), unknown);
});

test('buildLocalOnlyStatusUrl keeps the existing backend status path', () => {
  assert.equal(
    buildLocalOnlyStatusUrl('http://127.0.0.1:8123'),
    `http://127.0.0.1:8123${LOCAL_ONLY_STATUS_PATH}`
  );
  assert.equal(
    buildLocalOnlyStatusUrl('http://127.0.0.1:8123/?desktop_version=0.1.0'),
    `http://127.0.0.1:8123${LOCAL_ONLY_STATUS_PATH}`
  );
  assert.equal(buildLocalOnlyStatusUrl(''), null);
  assert.equal(buildLocalOnlyStatusUrl('not-a-url'), null);
  assert.equal(buildLocalOnlyStatusUrl('file:///tmp/loading.html'), null);
});
