// Only same-origin absolute paths are allowed; anything else (external URLs,
// protocol-relative "//host", backslash tricks) falls back to the home page.
export function resolveLoginRedirect(search: string | URLSearchParams): string {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search;
  const raw = params.get('redirect') ?? '';
  if (raw.startsWith('/') && !raw.startsWith('//') && !raw.startsWith('/\\')) {
    return raw;
  }
  return '/';
}
