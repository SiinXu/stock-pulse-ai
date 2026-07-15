const MODEL_REF_PREFIX = 'modelref:v1:';

export interface DecodedModelRef {
  connectionId: string;
  runtimeRoute: string;
}

const encodePart = (value: string): string => encodeURIComponent(value)
  .replace(/[!'()*]/g, (character) => `%${character.charCodeAt(0).toString(16).toUpperCase()}`);

export function encodeModelRef(connectionId: string, runtimeRoute: string): string {
  const normalizedConnectionId = connectionId.trim();
  const normalizedRuntimeRoute = runtimeRoute.trim();
  if (!normalizedConnectionId || !normalizedRuntimeRoute) {
    throw new Error('connectionId and runtimeRoute are required');
  }
  return `${MODEL_REF_PREFIX}${encodePart(normalizedConnectionId)}:${encodePart(normalizedRuntimeRoute)}`;
}

export function decodeModelRef(value: string): DecodedModelRef | null {
  const normalized = value.trim();
  if (!normalized.startsWith(MODEL_REF_PREFIX)) {
    return null;
  }
  const payload = normalized.slice(MODEL_REF_PREFIX.length);
  const separatorIndex = payload.indexOf(':');
  if (separatorIndex < 0) {
    return null;
  }
  try {
    const connectionId = decodeURIComponent(payload.slice(0, separatorIndex)).trim();
    const runtimeRoute = decodeURIComponent(payload.slice(separatorIndex + 1)).trim();
    return connectionId && runtimeRoute ? { connectionId, runtimeRoute } : null;
  } catch {
    return null;
  }
}

export function isVersionedModelRef(value: string): boolean {
  return value.trim().startsWith(MODEL_REF_PREFIX);
}
