import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../../api/error';
import { historyApi } from '../../../api/history';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ShareImageButton } from '../ShareImageButton';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getShareImage: vi.fn(),
  },
}));

const mockedGetShareImage = vi.mocked(historyApi.getShareImage);

function renderShareButton(props: {
  recordId?: number;
  reportTitle?: string;
  reportLanguage?: 'zh' | 'en' | 'ko';
}) {
  return render(
    <UiLanguageProvider initialLanguage="zh">
      <ShareImageButton
        recordId={props.recordId ?? 17}
        reportTitle={props.reportTitle ?? '中钨高新-000657'}
        reportLanguage={props.reportLanguage ?? 'zh'}
      />
    </UiLanguageProvider>,
  );
}

describe('ShareImageButton', () => {
  beforeEach(() => {
    vi.useRealTimers();
    mockedGetShareImage.mockReset();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:share-image');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    Object.defineProperty(window, 'dsaDesktop', { configurable: true, value: undefined });
    Object.defineProperty(navigator, 'share', { configurable: true, value: undefined });
    Object.defineProperty(navigator, 'canShare', { configurable: true, value: undefined });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('downloads the generated PNG when native file sharing is unavailable', async () => {
    mockedGetShareImage.mockResolvedValue(new Blob(['png'], { type: 'image/png' }));
    const appendSpy = vi.spyOn(document.body, 'appendChild');
    const removeSpy = vi.spyOn(document.body, 'removeChild');

    renderShareButton({ recordId: 17, reportTitle: '中钨高新-000657' });

    expect(mockedGetShareImage).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '分享' }));
    await waitFor(() => expect(mockedGetShareImage).toHaveBeenCalledWith(17));
    await waitFor(() => expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled());
    expect(appendSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:share-image');
    expect(screen.getByRole('button', { name: '已生成' })).toBeInTheDocument();
  });

  it('prepares the PNG on the first click and invokes native sharing synchronously on the second click', async () => {
    const nativeShare = vi.fn().mockResolvedValue(undefined);
    let resolveImage: ((blob: Blob) => void) | undefined;
    mockedGetShareImage.mockReturnValue(new Promise((resolve) => {
      resolveImage = resolve;
    }));
    Object.defineProperty(navigator, 'share', { configurable: true, value: nativeShare });
    Object.defineProperty(navigator, 'canShare', { configurable: true, value: () => true });

    renderShareButton({ recordId: 18, reportTitle: 'A股市场复盘' });

    expect(screen.getByRole('button', { name: '分享' })).toBeEnabled();
    expect(mockedGetShareImage).not.toHaveBeenCalled();
    expect(nativeShare).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '分享' }));
    expect(mockedGetShareImage).toHaveBeenCalledWith(18);
    expect(screen.getByRole('button', { name: '生成中...' })).toBeDisabled();
    expect(nativeShare).not.toHaveBeenCalled();

    await act(async () => {
      resolveImage?.(new Blob(['png'], { type: 'image/png' }));
    });

    expect(screen.getByRole('button', { name: '再次点击分享' })).toBeEnabled();
    expect(nativeShare).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '再次点击分享' }));
    expect(nativeShare).toHaveBeenCalledTimes(1);
    const sharePayload = nativeShare.mock.calls[0][0];
    expect(sharePayload.title).toBe('A股市场复盘');
    expect(sharePayload.files[0].name).toBe('A股市场复盘-18.png');
    expect(mockedGetShareImage).toHaveBeenCalledTimes(1);
  });

  it('downloads the PNG when native file sharing rejects', async () => {
    const nativeShare = vi.fn().mockRejectedValue(new Error('activation expired'));
    mockedGetShareImage.mockResolvedValue(new Blob(['png'], { type: 'image/png' }));
    Object.defineProperty(navigator, 'share', { configurable: true, value: nativeShare });
    Object.defineProperty(navigator, 'canShare', { configurable: true, value: () => true });

    renderShareButton({ recordId: 20, reportTitle: 'A股市场复盘' });

    expect(mockedGetShareImage).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole('button', { name: '分享' }));

    expect(await screen.findByRole('button', { name: '再次点击分享' })).toBeEnabled();
    expect(nativeShare).not.toHaveBeenCalled();
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '再次点击分享' }));
    await waitFor(() => expect(nativeShare).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: '已生成' })).toBeInTheDocument();
  });

  it('shows localized 413 share_image_content_too_large guidance instead of a bare Retry label', async () => {
    mockedGetShareImage.mockRejectedValue(
      createApiError(
        createParsedApiError({
          title: '报告内容过长，无法生成分享图片',
          message: '当前报告有 120000 个字符，超过分享图片上限 100000。可在设置中提高 SHARE_IMAGE_MAX_CHARS，或缩短报告后再试。',
          status: 413,
          code: 'share_image_content_too_large',
          params: { limit: 100000, actual: 120000 },
          category: 'http_error',
        }),
      ),
    );

    renderShareButton({ recordId: 19, reportTitle: '中钨高新' });

    fireEvent.click(screen.getByRole('button', { name: '分享' }));
    const errorRegion = await screen.findByTestId('share-image-error');
    // Share button + ApiErrorAlert action both use the Retry label.
    expect(screen.getAllByRole('button', { name: '重试' }).length).toBeGreaterThanOrEqual(1);
    expect(errorRegion).toHaveTextContent('报告内容过长，无法生成分享图片');
    expect(errorRegion).toHaveTextContent('120000');
    expect(errorRegion).toHaveTextContent('100000');
    expect(errorRegion).toHaveTextContent('SHARE_IMAGE_MAX_CHARS');
    // Visual evidence substitute (AGENTS.md): component-test rendered DOM for the 413 state.
    expect(errorRegion).toMatchSnapshot('share-image-413-content-too-large');
  });

  it('shows localized 503 share_image_unavailable install guidance', async () => {
    mockedGetShareImage.mockRejectedValue(
      createApiError(
        createParsedApiError({
          title: '分享图片引擎不可用',
          message: '请检查转图工具是否已安装并可用。Playwright 引擎需要：cd apps/dsa-web && npm ci && npx playwright install chromium。',
          status: 503,
          code: 'share_image_unavailable',
          category: 'http_error',
        }),
      ),
    );

    renderShareButton({ recordId: 24, reportTitle: '中钨高新' });

    fireEvent.click(screen.getByRole('button', { name: '分享' }));
    const errorRegion = await screen.findByTestId('share-image-error');
    expect(errorRegion).toHaveTextContent('分享图片引擎不可用');
    expect(errorRegion).toHaveTextContent('playwright install chromium');
    expect(errorRegion).toMatchSnapshot('share-image-503-renderer-unavailable');
  });

  it('shows timeout guidance when share-image generation times out', async () => {
    mockedGetShareImage.mockRejectedValue(
      createApiError(
        createParsedApiError({
          title: '连接上游服务超时',
          message: '服务端访问外部依赖时超时，请稍后重试，或检查当前网络与代理设置。',
          category: 'upstream_timeout',
          code: 'ECONNABORTED',
        }),
        { code: 'ECONNABORTED' },
      ),
    );

    renderShareButton({ recordId: 25, reportTitle: '中钨高新' });

    fireEvent.click(screen.getByRole('button', { name: '分享' }));
    const errorRegion = await screen.findByTestId('share-image-error');
    expect(errorRegion).toHaveTextContent('超时');
    expect(errorRegion).toMatchSnapshot('share-image-timeout');
  });

  it('does not render or prefetch share images during desktop runtime', () => {
    mockedGetShareImage.mockResolvedValue(new Blob(['png'], { type: 'image/png' }));
    Object.defineProperty(window, 'dsaDesktop', {
      configurable: true,
      value: { version: '1.0.0' },
    });

    renderShareButton({ recordId: 23, reportTitle: '桌面端报告' });

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(mockedGetShareImage).not.toHaveBeenCalled();
  });

  it('clears the previous success reset timer when switching to another record', async () => {
    vi.useFakeTimers();
    const nativeShare = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'share', { configurable: true, value: nativeShare });
    Object.defineProperty(navigator, 'canShare', { configurable: true, value: () => true });
    const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout');
    let resolveSecondImage: ((blob: Blob) => void) | undefined;
    mockedGetShareImage
      .mockResolvedValueOnce(new Blob(['a'], { type: 'image/png' }))
      .mockReturnValueOnce(new Promise((resolve) => {
        resolveSecondImage = resolve;
      }));

    const { rerender } = render(
      <UiLanguageProvider initialLanguage="zh">
        <ShareImageButton
          recordId={21}
          reportTitle="报告A"
          reportLanguage="zh"
        />
      </UiLanguageProvider>,
    );

    expect(mockedGetShareImage).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '分享' })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '分享' }));
      await Promise.resolve();
    });

    expect(mockedGetShareImage).toHaveBeenCalledWith(21);
    expect(nativeShare).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '再次点击分享' })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '再次点击分享' }));
      await Promise.resolve();
    });

    expect(nativeShare).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: '已生成' })).toBeInTheDocument();

    rerender(
      <UiLanguageProvider initialLanguage="zh">
        <ShareImageButton
          recordId={22}
          reportTitle="报告B"
          reportLanguage="zh"
        />
      </UiLanguageProvider>,
    );

    expect(screen.getByRole('button', { name: '分享' })).toBeEnabled();
    expect(mockedGetShareImage).not.toHaveBeenCalledWith(22);
    fireEvent.click(screen.getByRole('button', { name: '分享' }));
    expect(screen.getByRole('button', { name: '生成中...' })).toBeDisabled();
    await act(async () => {
      resolveSecondImage?.(new Blob(['b'], { type: 'image/png' }));
      await Promise.resolve();
    });

    expect(mockedGetShareImage).toHaveBeenCalledWith(22);
    expect(screen.getByRole('button', { name: '再次点击分享' })).toBeInTheDocument();
    expect(clearTimeoutSpy).toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '再次点击分享' }));
      await Promise.resolve();
    });

    expect(nativeShare).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: '已生成' })).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(2300);
    });

    expect(screen.getByRole('button', { name: '分享' })).toBeInTheDocument();
  });
});
