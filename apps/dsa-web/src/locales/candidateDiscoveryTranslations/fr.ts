// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// PENDING_NATIVE_REVIEW: High-risk financial discovery copy requires native-language review.
import type { CandidateDiscoveryText } from '../candidateDiscoveryText';

const translations: CandidateDiscoveryText = {
  documentTitle: "Découvrir - StockPulse",
  pageTitle: "Découvrir",
  pageDescription: "Découverte bornée de candidats par IA, ou AlphaSift en option, sur la même page. Recherche uniquement — pas d'instruction de trading.",
  discoveryStatusReady: "Découverte IA prête (bornée)",
  modeStrategy: "Criblage stratégique",
  modeDiscovery: "Découverte IA",
  discoveryTitle: "Découverte de candidats IA (bornée)",
  discoveryDescription: "Trouvez des candidats via langage naturel ou critères sur watchlist, portefeuille ou index de symboles paginé. Cotations via data_provider avec budget — pas de scan marché illimité.",
  discoveryDisclaimer: "Criblage de recherche uniquement. Pas un conseil d'investissement ni une instruction de trading.",
  discoveryQuery: "Langage naturel / critères",
  discoveryQueryPlaceholder: "ex. banques variation > 2 montant > 100m",
  discoveryUniverse: "Univers",
  discoveryUniverseWatchlist: "Liste de suivi",
  discoveryUniversePortfolio: "Portefeuille",
  discoveryUniverseIndex: "Page d'index des symboles",
  discoveryPage: "N° de page",
  discoveryPageSize: "Taille de page",
  discoveryMaxResults: "Résultats max.",
  discoveryProviderBudget: "Budget d'appels fournisseur",
  discoveryRun: "Lancer la découverte",
  discoveryRunning: "Découverte en cours…",
  discoverySubmitting: "Soumission de la tâche de découverte…",
  discoveryCancel: "Annuler",
  discoveryCancelRequested: "Annulation demandée",
  discoveryCancelFailed: "Échec de l'annulation",
  discoveryFailed: "Échec de la découverte de candidats",
  discoveryNoHits: "Aucun candidat pour cet univers et ces critères.",
  discoveryProgress: "Progression {progress}% · {message}",
  discoveryCostSummary: "Coût : cotations {provider}/{maxProvider} · candidats {candidates}",
  discoveryUniverseSummary: "Univers {source} · résolus {resolved} · évalués {evaluated}",
  discoveryAddWatchlist: "Ajouter à la watchlist",
  discoveryWatchlistAdded: "Ajouté à la watchlist : {code}",
  discoveryWatchlistFailed: "Échec d'ajout à la watchlist",
};

export default translations;
