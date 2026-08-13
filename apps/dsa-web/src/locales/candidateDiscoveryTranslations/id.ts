// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// PENDING_NATIVE_REVIEW: High-risk financial discovery copy requires native-language review.
import type { CandidateDiscoveryText } from '../candidateDiscoveryText';

const translations: CandidateDiscoveryText = {
  documentTitle: "Temukan - StockPulse",
  pageTitle: "Temukan",
  pageDescription: "Penemuan kandidat AI terbatas atau AlphaSift opsional di halaman yang sama. Hanya riset — bukan instruksi trading.",
  discoveryStatusReady: "Penemuan AI siap (terbatas)",
  modeStrategy: "Skrining strategi",
  modeDiscovery: "Penemuan AI",
  discoveryTitle: "Penemuan kandidat AI (terbatas)",
  discoveryDescription: "Temukan kandidat lewat bahasa alami/kriteria di watchlist, portofolio, atau indeks simbol berhalaman. Kuotasi via data_provider beranggaran — tanpa pindaian pasar tanpa batas.",
  discoveryDisclaimer: "Hanya skrining riset. Bukan saran investasi atau instruksi trading.",
  discoveryQuery: "Bahasa alami / kriteria",
  discoveryQueryPlaceholder: "mis. bank perubahan > 2 nilai > 100m",
  discoveryUniverse: "Universum",
  discoveryUniverseWatchlist: "Daftar pantau",
  discoveryUniversePortfolio: "Portofolio",
  discoveryUniverseIndex: "Halaman indeks simbol",
  discoveryPage: "Halaman",
  discoveryPageSize: "Ukuran halaman",
  discoveryMaxResults: "Hasil maks.",
  discoveryProviderBudget: "Anggaran panggilan penyedia",
  discoveryRun: "Jalankan penemuan",
  discoveryRunning: "Penemuan berjalan…",
  discoverySubmitting: "Mengirim tugas penemuan…",
  discoveryCancel: "Batal",
  discoveryCancelRequested: "Pembatalan diminta",
  discoveryCancelFailed: "Gagal membatalkan",
  discoveryFailed: "Penemuan kandidat gagal",
  discoveryNoHits: "Tidak ada kandidat untuk universum dan kriteria ini.",
  discoveryProgress: "Progres {progress}% · {message}",
  discoveryCostSummary: "Biaya: kuotasi {provider}/{maxProvider} · kandidat {candidates}",
  discoveryUniverseSummary: "Universum {source} · terselesaikan {resolved} · dievaluasi {evaluated}",
  discoveryAddWatchlist: "Tambah ke watchlist",
  discoveryWatchlistAdded: "Ditambahkan ke watchlist: {code}",
  discoveryWatchlistFailed: "Gagal menambah watchlist",
};

export default translations;
