const MODEL_REF_PREFIX = 'modelref:v1:';

function encodePart(value: string): string {
  return encodeURIComponent(value).replace(/[!'()*]/g, (character) => (
    `%${character.charCodeAt(0).toString(16).toUpperCase()}`
  ));
}

/** Build the versioned opaque model identity shared with `src.llm.model_ref`. */
export function encodeModelRef(connectionId: string, runtimeRoute: string): string {
  const normalizedConnectionId = connectionId.trim();
  const normalizedRuntimeRoute = runtimeRoute.trim();
  if (!normalizedConnectionId || !normalizedRuntimeRoute) {
    throw new Error('connectionId and runtimeRoute are required');
  }
  return `${MODEL_REF_PREFIX}${encodePart(normalizedConnectionId)}:${encodePart(normalizedRuntimeRoute)}`;
}

export function isModelRef(value: string): boolean {
  return value.trim().startsWith(MODEL_REF_PREFIX);
}
