import type {
  SystemConfigFieldSchema,
  SystemConfigUIPlacement,
} from '../types/systemConfig';

const KNOWN_UI_PLACEMENTS = new Set<SystemConfigUIPlacement>([
  'model_access',
  'task_routing',
  'developer_diagnostics',
  'hidden_legacy',
]);

export type ResolvedSystemConfigPlacement = SystemConfigUIPlacement | 'generic';
export type SystemConfigPlacementDiagnostic =
  | 'missing_ai_ui_placement'
  | 'unknown_ui_placement';

export interface SystemConfigFieldPlacementResolution {
  placement: ResolvedSystemConfigPlacement;
  readOnly: boolean;
  diagnostic: SystemConfigPlacementDiagnostic | null;
}

/**
 * Interpret backend field ownership without letting a rolling-deploy or stale
 * Desktop schema recreate a generic AI-model form. Regular fields may omit a
 * placement; AI fields may not. Unknown future placements are kept visible in
 * diagnostics, but never editable by an older client.
 */
export function resolveSystemConfigFieldPlacement(
  schema: Pick<SystemConfigFieldSchema, 'category' | 'uiPlacement'>,
): SystemConfigFieldPlacementResolution {
  const placement = schema.uiPlacement as string | null | undefined;
  if (placement && KNOWN_UI_PLACEMENTS.has(placement as SystemConfigUIPlacement)) {
    return {
      placement: placement as SystemConfigUIPlacement,
      readOnly: false,
      diagnostic: null,
    };
  }
  if (placement) {
    return {
      placement: 'developer_diagnostics',
      readOnly: true,
      diagnostic: 'unknown_ui_placement',
    };
  }
  if (schema.category === 'ai_model') {
    return {
      placement: 'developer_diagnostics',
      readOnly: true,
      diagnostic: 'missing_ai_ui_placement',
    };
  }
  return { placement: 'generic', readOnly: false, diagnostic: null };
}
