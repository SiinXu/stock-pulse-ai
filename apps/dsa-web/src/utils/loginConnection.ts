export type LoginConnectionStatus = 'secure' | 'local' | 'insecure';

const LOOPBACK_HOSTNAMES = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);

export function getLoginConnectionStatus(protocol: string, hostname: string): LoginConnectionStatus {
  if (protocol === 'https:') {
    return 'secure';
  }
  if (LOOPBACK_HOSTNAMES.has(hostname.toLowerCase())) {
    return 'local';
  }
  return 'insecure';
}
