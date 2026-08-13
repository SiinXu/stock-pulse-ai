// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// PENDING_NATIVE_REVIEW: High-risk financial discovery copy requires native-language review.
import type { CandidateDiscoveryText } from '../candidateDiscoveryText';

const translations: CandidateDiscoveryText = {
  documentTitle: "Descubrir - StockPulse",
  pageTitle: "Descubrir",
  pageDescription: "Descubrimiento acotado de candidatos con IA u opcionalmente AlphaSift en la misma página. Solo investigación, no órdenes de trading.",
  discoveryStatusReady: "Descubrimiento IA listo (acotado)",
  modeStrategy: "Cribado por estrategia",
  modeDiscovery: "Descubrimiento IA",
  discoveryTitle: "Descubrimiento de candidatos con IA (acotado)",
  discoveryDescription: "Encuentra candidatos con lenguaje natural o criterios en lista de seguimiento, cartera o índice de símbolos paginado. Cotizaciones vía data_provider con presupuesto: sin escaneo ilimitado del mercado.",
  discoveryDisclaimer: "Solo cribado de investigación. No es consejo de inversión ni instrucción de trading.",
  discoveryQuery: "Lenguaje natural / criterios",
  discoveryQueryPlaceholder: "p. ej. bancos cambio > 2 importe > 100m",
  discoveryUniverse: "Universo",
  discoveryUniverseWatchlist: "Lista de seguimiento",
  discoveryUniversePortfolio: "Cartera",
  discoveryUniverseIndex: "Página del índice de símbolos",
  discoveryPage: "Página",
  discoveryPageSize: "Tamaño de página",
  discoveryMaxResults: "Máx. resultados",
  discoveryProviderBudget: "Presupuesto de llamadas al proveedor",
  discoveryRun: "Ejecutar descubrimiento",
  discoveryRunning: "Descubrimiento en curso…",
  discoverySubmitting: "Enviando tarea de descubrimiento…",
  discoveryCancel: "Cancelar",
  discoveryCancelRequested: "Cancelación solicitada",
  discoveryCancelFailed: "No se pudo cancelar",
  discoveryFailed: "Falló el descubrimiento de candidatos",
  discoveryNoHits: "Ningún candidato coincide con este universo y criterios.",
  discoveryProgress: "Progreso {progress}% · {message}",
  discoveryCostSummary: "Coste: cotizaciones {provider}/{maxProvider} · candidatos {candidates}",
  discoveryUniverseSummary: "Universo {source} · resueltos {resolved} · evaluados {evaluated}",
  discoveryAddWatchlist: "Añadir a la lista",
  discoveryWatchlistAdded: "Añadido a la lista: {code}",
  discoveryWatchlistFailed: "No se pudo añadir a la lista",
};

export default translations;
