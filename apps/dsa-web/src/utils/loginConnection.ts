export type LoginConnectionStatus = 'https' | 'local-http' | 'insecure-http';

type LoginLocation = Pick<Location, 'hostname' | 'protocol'>;

function normalizeHostname(hostname: string): string {
  const normalized = hostname.toLowerCase().replace(/\.$/, '');
  if (normalized.startsWith('[') && normalized.endsWith(']')) {
    return normalized.slice(1, -1);
  }
  return normalized;
}

function isIpv4Loopback(hostname: string): boolean {
  const octets = hostname.split('.');
  if (octets.length !== 4 || octets[0] !== '127') return false;
  return octets.every((octet) => {
    if (!/^\d{1,3}$/.test(octet)) return false;
    const value = Number(octet);
    return value >= 0 && value <= 255;
  });
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = normalizeHostname(hostname);
  return normalized === 'localhost'
    || normalized.endsWith('.localhost')
    || normalized === '::1'
    || isIpv4Loopback(normalized);
}

export function getLoginConnectionStatus(location: LoginLocation): LoginConnectionStatus {
  if (location.protocol.toLowerCase() === 'https:') return 'https';
  if (location.protocol.toLowerCase() === 'http:' && isLoopbackHostname(location.hostname)) {
    return 'local-http';
  }
  return 'insecure-http';
}
