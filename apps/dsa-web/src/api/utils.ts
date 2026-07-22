import camelcaseKeys from 'camelcase-keys';

/**
 * Convert snake_case object keys to camelCase
 * @param data API Response Data (snake_case)
 * @returns The converted camelCase object
 */
export function toCamelCase<T>(data: unknown): T {
    if (data === null || data === undefined) {
        return data as T;
    }
    return camelcaseKeys(data as Record<string, unknown>, { deep: true }) as T;
}
