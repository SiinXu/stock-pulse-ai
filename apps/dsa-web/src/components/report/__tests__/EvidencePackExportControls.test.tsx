// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../../api/error';
import { evidencePackExportApi } from '../../../api/evidencePackExport';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import EvidencePackExportControls from '../EvidencePackExportControls';

vi.mock('../../../api/evidencePackExport', () => ({
  evidencePackExportApi: {
    downloadEvidenceChain: vi.fn(),
    downloadAuditPackage: vi.fn(),
  },
}));

function renderControls() {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <EvidencePackExportControls recordId={42} />
    </UiLanguageProvider>,
  );
}

describe('EvidencePackExportControls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('downloads evidence-chain JSON and audit ZIP through their canonical APIs', async () => {
    const result = {
      filename: 'audit-package-42.zip',
      truncated: false,
      contentType: 'application/zip',
      byteLength: 128,
    };
    vi.mocked(evidencePackExportApi.downloadEvidenceChain).mockResolvedValue(result);
    vi.mocked(evidencePackExportApi.downloadAuditPackage).mockResolvedValue(result);
    renderControls();

    fireEvent.click(screen.getByTestId('evidence-chain-export-json'));
    await waitFor(() => {
      expect(evidencePackExportApi.downloadEvidenceChain).toHaveBeenCalledWith(42);
    });
    fireEvent.click(screen.getByTestId('audit-package-export-zip'));
    await waitFor(() => {
      expect(evidencePackExportApi.downloadAuditPackage).toHaveBeenCalledWith(42, 'zip');
    });
  });

  it('keeps controls visible and links to settings when export is disabled', async () => {
    const parsed = createParsedApiError({
      title: 'Audit package export is disabled',
      message: 'Enable AUDIT_EXPORT_ENABLED under Settings.',
      rawMessage: 'disabled',
      status: 404,
      category: 'http_error',
      code: 'audit_export_disabled',
    });
    vi.mocked(evidencePackExportApi.downloadAuditPackage).mockRejectedValue(createApiError(parsed));
    renderControls();

    fireEvent.click(screen.getByTestId('audit-package-export-zip'));
    expect(await screen.findByTestId('evidence-pack-export-disabled')).toBeInTheDocument();
    expect(screen.getByTestId('evidence-pack-export-settings-link')).toHaveAttribute(
      'href', expect.stringContaining('/settings'),
    );
    expect(screen.getByTestId('audit-package-export-zip')).toBeInTheDocument();
  });

  it('surfaces package truncation without reporting success as complete', async () => {
    vi.mocked(evidencePackExportApi.downloadAuditPackage).mockResolvedValue({
      filename: 'audit-package-42.zip',
      truncated: true,
      contentType: 'application/zip',
      byteLength: 5000,
    });
    renderControls();

    fireEvent.click(screen.getByTestId('audit-package-export-zip'));
    expect(await screen.findByTestId('evidence-pack-export-truncated')).toBeInTheDocument();
  });
});
