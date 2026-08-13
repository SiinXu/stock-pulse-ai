// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// PENDING_NATIVE_REVIEW: High-risk financial discovery copy requires native-language review.
import type { CandidateDiscoveryText } from '../candidateDiscoveryText';

const translations: CandidateDiscoveryText = {
  documentTitle: "Temui - StockPulse",
  pageTitle: "Temui",
  pageDescription: "Penemuan calon AI terhad atau AlphaSift pilihan pada halaman yang sama. Untuk penyelidikan sahaja — bukan arahan dagangan.",
  discoveryStatusReady: "Penemuan AI sedia (terhad)",
  modeStrategy: "Saringan strategi",
  modeDiscovery: "Penemuan AI",
  discoveryTitle: "Penemuan calon AI (terhad)",
  discoveryDescription: "Cari calon melalui bahasa semula jadi/kriteria dalam senarai pantau, portfolio atau indeks simbol berhalaman. Sebut harga melalui data_provider dengan bajet — tiada imbasan pasaran tanpa had.",
  discoveryDisclaimer: "Saringan penyelidikan sahaja. Bukan nasihat pelaburan atau arahan dagangan.",
  discoveryQuery: "Bahasa semula jadi / kriteria",
  discoveryQueryPlaceholder: "cth. bank perubahan > 2 jumlah > 100m",
  discoveryUniverse: "Alam semesta",
  discoveryUniverseWatchlist: "Senarai pantau",
  discoveryUniversePortfolio: "Portfolio dagangan",
  discoveryUniverseIndex: "Halaman indeks simbol",
  discoveryPage: "Halaman",
  discoveryPageSize: "Saiz halaman",
  discoveryMaxResults: "Keputusan maks.",
  discoveryProviderBudget: "Bajet panggilan pembekal",
  discoveryRun: "Jalankan penemuan",
  discoveryRunning: "Penemuan sedang berjalan…",
  discoverySubmitting: "Menghantar tugas penemuan…",
  discoveryCancel: "Batal",
  discoveryCancelRequested: "Pembatalan diminta",
  discoveryCancelFailed: "Gagal membatalkan",
  discoveryFailed: "Penemuan calon gagal",
  discoveryNoHits: "Tiada calon sepadan dengan alam semesta dan kriteria ini.",
  discoveryProgress: "Kemajuan {progress}% · {message}",
  discoveryCostSummary: "Kos: sebut harga {provider}/{maxProvider} · calon {candidates}",
  discoveryUniverseSummary: "Alam semesta {source} · diselesaikan {resolved} · dinilai {evaluated}",
  discoveryAddWatchlist: "Tambah ke senarai pantau",
  discoveryWatchlistAdded: "Ditambah ke senarai pantau: {code}",
  discoveryWatchlistFailed: "Gagal menambah senarai pantau",
};

export default translations;
