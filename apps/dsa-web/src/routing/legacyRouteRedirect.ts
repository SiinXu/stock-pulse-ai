// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

type LegacyLocation = {
  search: string;
  hash: string;
};

export type LegacySearchParamsMapper = (searchParams: URLSearchParams) => void;

export type LegacyRouteRedirectOptions = {
  mapSearchParams?: LegacySearchParamsMapper;
  overrideSearchParams?: Readonly<Record<string, string | null | undefined>>;
};

export function resolveLegacyRouteRedirect(
  location: LegacyLocation,
  pathname: string,
  options: LegacyRouteRedirectOptions = {},
): { pathname: string; search: string; hash: string } {
  const searchParams = new URLSearchParams(location.search);
  options.mapSearchParams?.(searchParams);
  for (const [key, value] of Object.entries(options.overrideSearchParams ?? {})) {
    if (value === null || value === undefined) {
      searchParams.delete(key);
    } else {
      searchParams.set(key, value);
    }
  }
  const search = searchParams.toString();
  return {
    pathname,
    search: search ? `?${search}` : '',
    hash: location.hash,
  };
}
