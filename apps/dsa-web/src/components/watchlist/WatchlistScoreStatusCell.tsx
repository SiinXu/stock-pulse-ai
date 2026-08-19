// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

// Default-export facade so WatchlistGroupsPanel can `lazy(() => import(...))`
// this cell without inlining WatchlistScoreColumn into the Home groups chunk.
export { WatchlistScoreStatusCell as default } from './WatchlistScoreColumn';
