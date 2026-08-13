// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// PENDING_NATIVE_REVIEW: High-risk financial discovery copy requires native-language review.
import type { CandidateDiscoveryText } from '../candidateDiscoveryText';

const translations: CandidateDiscoveryText = {
  documentTitle: "Entdecken - StockPulse",
  pageTitle: "Entdecken",
  pageDescription: "Begrenzte KI-Kandidatensuche oder optional AlphaSift-Strategien auf derselben Seite. Nur Research – keine Handelsanweisung.",
  discoveryStatusReady: "KI-Entdeckung bereit (begrenzt)",
  modeStrategy: "Strategie-Screening",
  modeDiscovery: "KI-Entdeckung",
  discoveryTitle: "KI-Kandidatensuche (begrenzt)",
  discoveryDescription: "Finde Kandidaten per Sprache/Kriterien in Watchlist, Portfolio oder paginiertem Symbolindex. Quotes über data_provider mit Budget – kein unbegrenzter Markt-Scan.",
  discoveryDisclaimer: "Nur Research-Screening. Keine Anlageberatung und keine Handelsanweisung.",
  discoveryQuery: "Natürliche Sprache / Kriterien",
  discoveryQueryPlaceholder: "z. B. Banken Änderung > 2 Umsatz > 100m",
  discoveryUniverse: "Universum",
  discoveryUniverseWatchlist: "Beobachtungsliste",
  discoveryUniversePortfolio: "Depot",
  discoveryUniverseIndex: "Symbolindex-Seite",
  discoveryPage: "Seite",
  discoveryPageSize: "Seitengröße",
  discoveryMaxResults: "Max. Ergebnisse",
  discoveryProviderBudget: "Anbieter-Aufrufbudget",
  discoveryRun: "Entdeckung starten",
  discoveryRunning: "Entdeckung läuft…",
  discoverySubmitting: "Entdeckungsaufgabe wird gesendet…",
  discoveryCancel: "Abbrechen",
  discoveryCancelRequested: "Abbruch angefordert",
  discoveryCancelFailed: "Abbruch fehlgeschlagen",
  discoveryFailed: "Kandidatensuche fehlgeschlagen",
  discoveryNoHits: "Keine Treffer für dieses Universum und diese Kriterien.",
  discoveryProgress: "Fortschritt {progress}% · {message}",
  discoveryCostSummary: "Kosten: Quotes {provider}/{maxProvider} · Kandidaten {candidates}",
  discoveryUniverseSummary: "Universum {source} · aufgelöst {resolved} · bewertet {evaluated}",
  discoveryAddWatchlist: "Zur Watchlist",
  discoveryWatchlistAdded: "Zur Watchlist hinzugefügt: {code}",
  discoveryWatchlistFailed: "Watchlist-Hinzufügen fehlgeschlagen",
};

export default translations;
