import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Loader2, Share2, TriangleAlert } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { historyApi } from '../../api/history';
import type { ReportLanguage } from '../../types/analysis';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import { ApiErrorAlert } from '../common/ApiErrorAlert';
import { Tooltip } from '../common/Tooltip';

type ShareState = 'idle' | 'loading' | 'ready' | 'success' | 'error';

interface ShareImageButtonProps {
  recordId?: number;
  reportTitle: string;
  reportLanguage?: ReportLanguage;
  className?: string;
}

const safeFilenamePart = (value: string): string => {
  const normalized = value.trim().replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, '-');
  return normalized.slice(0, 72) || 'report';
};

/** DOM-attached synchronous download (matches chatExport / Settings / ConfigBackup patterns for Firefox/Safari and desktop WebView). */
const downloadBlob = (blob: Blob, filename: string): void => {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
};

export const ShareImageButton: React.FC<ShareImageButtonProps> = ({
  recordId,
  reportTitle,
  reportLanguage = 'zh',
  className = '',
}) => {
  // Desktop (window.dsaDesktop) uses the same on-click path as pure Web: no mount-time
  // prefetch. When navigator.share/canShare is absent (typical Electron WebView), the
  // existing downloadBlob helper falls back to a[download] + blob, which the desktop
  // navigation guard already preserves.
  const text = getReportText(normalizeReportLanguage(reportLanguage));
  const [stateSnapshot, setStateSnapshot] = useState<{
    recordId?: number;
    state: ShareState;
    error: ParsedApiError | null;
  }>(() => ({
    recordId,
    state: 'idle',
    error: null,
  }));
  const resetTimerRef = useRef<number | null>(null);
  const loadTokenRef = useRef(0);
  const cachedImageRef = useRef<{ recordId: number; blob: Blob } | null>(null);
  const state = stateSnapshot.recordId === recordId ? stateSnapshot.state : 'idle';
  const shareError = stateSnapshot.recordId === recordId ? stateSnapshot.error : null;
  const setState = useCallback((nextState: ShareState, nextError: ParsedApiError | null = null) => {
    setStateSnapshot({ recordId, state: nextState, error: nextError });
  }, [recordId]);
  const clearResetTimer = useCallback(() => {
    if (resetTimerRef.current !== null) {
      window.clearTimeout(resetTimerRef.current);
      resetTimerRef.current = null;
    }
  }, []);

  const scheduleReset = useCallback(() => {
    clearResetTimer();
    const scheduledRecordId = recordId;
    resetTimerRef.current = window.setTimeout(() => {
      setStateSnapshot((current) => (
        current.recordId === scheduledRecordId
          ? { recordId: scheduledRecordId, state: 'idle', error: null }
          : current
      ));
    }, 2200);
  }, [recordId, clearResetTimer]);

  useEffect(() => {
    clearResetTimer();
    loadTokenRef.current += 1;
    cachedImageRef.current = null;

    return () => {
      clearResetTimer();
      loadTokenRef.current += 1;
    };
  }, [recordId, clearResetTimer]);

  const handleShare = useCallback(async () => {
    if (recordId === undefined || state === 'loading') return;
    clearResetTimer();

    let blob = cachedImageRef.current?.recordId === recordId
      ? cachedImageRef.current.blob
      : null;
    let generatedNow = false;

    if (!blob) {
      const loadToken = loadTokenRef.current + 1;
      loadTokenRef.current = loadToken;
      setState('loading');
      try {
        blob = await historyApi.getShareImage(recordId);
      } catch (error) {
        if (loadTokenRef.current !== loadToken) return;
        console.error('Generate share image failed:', error);
        setState('error', getParsedApiError(error));
        return;
      }
      if (loadTokenRef.current !== loadToken) return;
      cachedImageRef.current = { recordId, blob };
      generatedNow = true;
    }

    const filename = `${safeFilenamePart(reportTitle)}-${recordId}.png`;
    const file = new File([blob], filename, { type: 'image/png' });
    const canShareFile = typeof navigator.share === 'function'
      && typeof navigator.canShare === 'function'
      && navigator.canShare({ files: [file] });

    // A file cannot be shared before it exists, while navigator.share() must run
    // inside a transient user-activation event. Prepare on the first click and
    // let the next click invoke native sharing synchronously.
    if (generatedNow && canShareFile) {
      setState('ready');
      return;
    }

    setState('loading');
    try {
      if (canShareFile) {
        try {
          await navigator.share({
            files: [file],
            title: reportTitle,
          });
        } catch (error) {
          if (error instanceof DOMException && error.name === 'AbortError') {
            setState('ready');
            return;
          }
          console.warn('Native file sharing failed; falling back to download:', error);
          downloadBlob(blob, filename);
        }
      } else {
        downloadBlob(blob, filename);
      }

      setState('success');
      scheduleReset();
    } catch (error) {
      console.error('Generate share image failed:', error);
      setState('error', getParsedApiError(error));
    }
  }, [recordId, clearResetTimer, reportTitle, scheduleReset, setState, state]);

  if (recordId === undefined) return null;

  const tooltipText = state === 'loading'
    ? text.generatingShareImage
    : state === 'ready'
      ? text.shareImageReadyToShare
    : state === 'success'
      ? text.shareImageReady
      : state === 'error'
        ? text.shareImageFailed
        : text.generateShareImage;

  return (
    <span className={`inline-flex max-w-full flex-col items-end gap-2 ${className}`.trim()}>
      <Tooltip content={tooltipText}>
        <span className="inline-flex shrink-0">
          <button
            type="button"
            onClick={() => void handleShare()}
            disabled={state === 'loading'}
            className="home-surface-button flex h-10 shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3 text-sm font-medium text-secondary-text hover:text-foreground disabled:opacity-50"
            aria-label={tooltipText}
          >
            {state === 'loading' ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> : null}
            {state === 'success' ? <Check className="h-5 w-5 text-success" aria-hidden="true" /> : null}
            {state === 'error' ? <TriangleAlert className="h-5 w-5 text-danger" aria-hidden="true" /> : null}
            {state === 'idle' || state === 'ready' ? <Share2 className="h-5 w-5" aria-hidden="true" /> : null}
            <span>{tooltipText}</span>
          </button>
        </span>
      </Tooltip>
      {state === 'error' && shareError ? (
        <ApiErrorAlert
          error={shareError}
          actionLabel={text.shareImageFailed}
          onAction={() => void handleShare()}
        />
      ) : null}
    </span>
  );
};
