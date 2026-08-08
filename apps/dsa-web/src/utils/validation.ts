interface ValidationResult {
  valid: boolean;
  message?: string;
  normalized: string;
}

const SUPPORTED_QUERY_CHARACTERS = /^[A-Z0-9.\u3400-\u9FFF\s]+$/;

const STOCK_CODE_PATTERNS = [
  /^\d{6}$/, // A-share 6-digit code
  /^(SH|SZ|BJ)\d{6}$/, // A-share code with exchange prefix
  /^\d{6}\.(SH|SZ|SS|BJ)$/, // A-share code with exchange suffix
  /^\d{4}$/, // HK 4-digit bare code, for example 0001 / 0941 / 1810
  /^\d{5}$/, // HK code without prefix
  /^HK\d{1,5}$/, // HK-prefixed code, for example HK00700
  /^\d{1,5}\.HK$/, // HK suffix format, for example 00700.HK
  /^\d{4,5}\.T$/, // Japan Yahoo suffix format, for example 7203.T
  /^\d{6}\.(KS|KQ)$/, // Korea Yahoo suffix format, for example 005930.KS or 035720.KQ
  /^[A-Z]{1,5}(?:\.(?:US|[A-Z]))?$/, // Common US ticker format
];

/**
 * Check whether the input looks like a stock code.
 */
export const looksLikeStockCode = (value: string): boolean => {
  const normalized = value.trim().toUpperCase();
  return STOCK_CODE_PATTERNS.some((regex) => regex.test(normalized));
};

/**
 * Validate common A-share, HK, US, JP, and KR stock code formats.
 *
 * Bare 4-digit codes are accepted as Hong Kong stocks and rewritten to the
 * explicit ``HKxxxxx`` form so API/watchlist callers that only consume the
 * ``normalized`` field still hit the shared HK identity (refs #2164).
 */
export const validateStockCode = (value: string): ValidationResult => {
  const upper = value.trim().toUpperCase();

  if (!upper) {
    return { valid: false, message: '请输入股票代码', normalized: upper };
  }

  const valid = looksLikeStockCode(upper);
  // Promote bare 4-digit HK codes at the validation boundary. Leave other
  // accepted forms as uppercase-only so existing 5/6-digit contracts stay
  // stable (5-digit bare HK remains "00700" here; normalizeStockCode may
  // still rewrite it at display/match call sites).
  const normalized =
    valid && /^\d{4}$/.test(upper) ? `HK${upper.padStart(5, '0')}` : upper;

  return {
    valid,
    message: valid ? undefined : '股票代码格式不正确',
    normalized,
  };
};

/**
 * Reject obviously invalid free-text queries before they reach the backend.
 */
export const isObviouslyInvalidStockQuery = (value: string): boolean => {
  const normalized = value.trim().toUpperCase();

  if (!normalized || looksLikeStockCode(normalized)) {
    return false;
  }

  if (!SUPPORTED_QUERY_CHARACTERS.test(normalized)) {
    return true;
  }

  const hasLetters = /[A-Z]/.test(normalized);
  const hasDigits = /\d/.test(normalized);

  return hasLetters && hasDigits;
};
