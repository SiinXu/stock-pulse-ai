// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
function domIdPart(value: string): string {
  return encodeURIComponent(value).replaceAll('%', '_');
}

export function getTabId(tabsId: string, value: string): string {
  return `${tabsId}--tab--${domIdPart(value)}`;
}

export function getTabPanelId(tabsId: string, value: string): string {
  return `${tabsId}--panel--${domIdPart(value)}`;
}
