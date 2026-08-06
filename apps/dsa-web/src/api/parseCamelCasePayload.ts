import { z } from 'zod';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';

/**
 * Convert a snake_case API body to camelCase, validate against a Zod schema, and
 * return the pre-validated camelCase object (not Zod's stripped output) so valid
 * payloads stay byte-identical to the historical unchecked cast path.
 *
 * On mismatch throw createApiError(createParsedApiError({ code:
 * 'api_response_validation_failed', ... })) for the existing ParsedApiError UX.
 */
export function parseCamelCasePayload<T>(
  data: unknown,
  schema: z.ZodTypeAny,
  label: string,
  logPrefix = 'api',
): T {
  const camel = toCamelCase<unknown>(data);
  return assertCamelCasePayload<T>(camel, schema, label, logPrefix);
}

/**
 * Validate an already-converted camelCase object (used when a module needs
 * custom post-toCamelCase shaping before the contract check).
 * Returns the same object reference on success.
 */
export function assertCamelCasePayload<T>(
  camel: unknown,
  schema: z.ZodTypeAny,
  label: string,
  logPrefix = 'api',
): T {
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    if (import.meta.env.DEV) {
      console.error(`[${logPrefix}] response validation failed (${label})`, result.error.issues);
    }
    throw createApiError(
      createParsedApiError({
        // Title/message are localized via STABLE_ERROR_TEXT[code] + params.
        title: '响应校验失败',
        message: `接口响应未通过校验（${label}）。${issueSummary}`,
        rawMessage: result.error.message,
        category: 'unknown',
        code: 'api_response_validation_failed',
        params: { label, issues: issueSummary },
        details: result.error.issues,
      }),
    );
  }
  return camel as T;
}
