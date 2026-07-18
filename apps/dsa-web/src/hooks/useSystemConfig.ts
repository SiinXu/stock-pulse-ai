import { useCallback, useMemo, useRef, useState } from 'react';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import { systemConfigApi, SystemConfigConflictError, SystemConfigValidationError } from '../api/systemConfig';
import type {
  ConfigConflictField,
  ConfigConflictState,
  ConfigValidationIssue,
  SystemConfigCategorySchema,
  SystemConfigItem,
  SystemConfigResponse,
  SystemConfigUpdateItem,
} from '../types/systemConfig';
import { serializeStockListValue } from '../utils/stockList';
import { getDefaultSubCategory, getSubCategories } from '../components/settings/settingsSubCategories';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { SETTINGS_PAGE_TEXT } from '../locales/settingsPage';

type ToastState = {
  type: 'success';
  message: string;
} | {
  type: 'error';
  error: ParsedApiError;
} | null;

type RetryAction = 'load' | 'save' | null;

type SaveResult = {
  success: boolean;
  message?: string;
  issues?: ConfigValidationIssue[];
};

const CATEGORY_DISPLAY_ORDER: Record<string, number> = {
  base: 10,
  ai_model: 20,
  data_source: 30,
  notification: 40,
  system: 50,
  agent: 55,
  backtest: 60,
  uncategorized: 99,
};

function sortItemsByOrder(items: SystemConfigItem[]): SystemConfigItem[] {
  return [...items].sort((a, b) => {
    const left = a.schema?.displayOrder ?? 9999;
    const right = b.schema?.displayOrder ?? 9999;
    if (left !== right) {
      return left - right;
    }
    return a.key.localeCompare(b.key);
  });
}

function isMultiValueSchema(schema: SystemConfigItem['schema'] | undefined): boolean {
  const validation = (schema?.validation ?? {}) as Record<string, unknown>;
  return Boolean(validation.multiValue ?? validation.multi_value);
}

function normalizeFieldValue(value: string, schema: SystemConfigItem['schema'] | undefined): string {
  if ((schema?.key ?? '').toUpperCase() === 'STOCK_LIST') {
    return serializeStockListValue(value);
  }

  if (!isMultiValueSchema(schema)) {
    return value;
  }

  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0)
    .join(',');
}

export function useSystemConfig(initialTab?: { category: string; subCategory: string | null }) {
  const { language, t } = useUiLanguage();
  // Server state
  const [configVersion, setConfigVersion] = useState<string>('');
  const [maskToken, setMaskToken] = useState<string>('******');
  const [serverItems, setServerItems] = useState<SystemConfigItem[]>([]);
  const [configuredNotificationChannels, setConfiguredNotificationChannels] = useState<string[] | null>(null);

  // UI state. The active tab may be seeded from the URL so deep links / refresh
  // restore the same category; applyServerPayload keeps it if the category loads.
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});
  const [activeCategory, setActiveCategory] = useState<string>(initialTab?.category ?? 'base');
  const [activeSubCategory, setActiveSubCategory] = useState<string | null>(initialTab?.subCategory ?? null);
  const activeCategoryRef = useRef<string>(initialTab?.category ?? 'base');
  const activeSubCategoryRef = useRef<string | null>(initialTab?.subCategory ?? null);
  const [validationIssues, setValidationIssues] = useState<ConfigValidationIssue[]>([]);
  const [toast, setToast] = useState<ToastState>(null);

  // Request state
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [saveError, setSaveError] = useState<ParsedApiError | null>(null);
  const [retryAction, setRetryAction] = useState<RetryAction>(null);
  const serverItemByKeyRef = useRef<Record<string, SystemConfigItem>>({});
  // Serializes config writes: a re-entrant save() reuses the in-flight promise
  // instead of submitting a second, stale-version transaction concurrently.
  const savePromiseRef = useRef<Promise<SaveResult> | null>(null);
  const loadRequestIdRef = useRef(0);
  // Every request that can produce a server snapshot shares this epoch. A
  // response may update server state only while it is still the newest such
  // request, regardless of whether it came from load, save, conflict recovery,
  // or an external-editor refresh.
  const serverSnapshotEpochRef = useRef(0);
  // Set when a save is rejected with a 409; carries the field-level three-way
  // diff (base/server/local) so the UI can resolve conflicts without clobbering.
  const [conflictState, setConflictState] = useState<ConfigConflictState | null>(null);

  const mergedItems = useMemo(() => {
    return sortItemsByOrder(
      serverItems.map((item) => ({
        ...item,
        value: draftValues[item.key] ?? item.value,
      })),
    );
  }, [draftValues, serverItems]);

  const serverItemByKey = useMemo(() => {
    const map: Record<string, SystemConfigItem> = {};
    for (const item of serverItems) {
      map[item.key] = item;
    }
    serverItemByKeyRef.current = map;
    return map;
  }, [serverItems]);

  const categories = useMemo<SystemConfigCategorySchema[]>(() => {
    // Infer tabs from loaded config item schema metadata.
    const categoryMap = new Map<string, SystemConfigCategorySchema>();
    for (const item of mergedItems) {
      if (!item.schema) {
        continue;
      }

      const category = item.schema.category;
      if (!categoryMap.has(category)) {
        categoryMap.set(category, {
          category,
          title: category.replace('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
          description: '',
          displayOrder: CATEGORY_DISPLAY_ORDER[category] ?? 999,
          fields: [],
        });
      }
      categoryMap.get(category)?.fields.push(item.schema);
    }

    return [...categoryMap.values()].sort((a, b) => a.displayOrder - b.displayOrder);
  }, [mergedItems]);

  const itemsByCategory = useMemo(() => {
    const map: Record<string, SystemConfigItem[]> = {};
    for (const item of mergedItems) {
      const category = item.schema?.category ?? 'uncategorized';
      if (!map[category]) {
        map[category] = [];
      }
      map[category].push(item);
    }
    return map;
  }, [mergedItems]);

  const dirtyKeys = useMemo(() => {
    const keys: string[] = [];
    for (const item of serverItems) {
      const draftRaw = draftValues[item.key];
      if (draftRaw === undefined) {
        continue;
      }

      const normalizedDraft = normalizeFieldValue(draftRaw, item.schema);
      const normalizedCurrent = normalizeFieldValue(item.value, item.schema);
      if (normalizedDraft !== normalizedCurrent) {
        keys.push(item.key);
      }
    }
    return keys;
  }, [draftValues, serverItems]);

  const hasDirty = dirtyKeys.length > 0;

  const issueByKey = useMemo(() => {
    const map: Record<string, ConfigValidationIssue[]> = {};
    for (const issue of validationIssues) {
      if (!map[issue.key]) {
        map[issue.key] = [];
      }
      map[issue.key].push(issue);
    }
    return map;
  }, [validationIssues]);

  const applyServerPayload = useCallback(
    (
      items: SystemConfigItem[],
      version: string,
      token: string,
      options?: {
        preserveDirty?: boolean;
        committedKeys?: string[];
        committedValues?: Record<string, string>;
        configuredNotificationChannels?: string[] | null;
      },
    ) => {
      const sorted = sortItemsByOrder(items);
      const previousServerMap = serverItemByKeyRef.current;
      const committedKeys = new Set(options?.committedKeys ?? []);
      const committedValues = options?.committedValues;
      const preserveDirty = options?.preserveDirty ?? false;

      setServerItems(sorted);
      setConfigVersion(version);
      setMaskToken(token || '******');
      setConfiguredNotificationChannels(options?.configuredNotificationChannels ?? null);

      setDraftValues((prevDraft) => {
        const nextDraft: Record<string, string> = {};
        for (const item of sorted) {
          if (committedKeys.has(item.key)) {
            // A key we just committed. If the user re-edited it while the save
            // was in flight, keep the newer edit; otherwise sync to the server.
            // Callers may also submit a value owned by a dedicated editor that
            // is not mirrored into draftValues. In that case currentDraft still
            // equals the old server value and must not overwrite the commit.
            const submitted = committedValues?.[item.key];
            const currentDraft = prevDraft[item.key];
            const previousServerValue = previousServerMap[item.key]?.value;
            if (
              submitted !== undefined
              && currentDraft !== undefined
              && currentDraft !== submitted
              && currentDraft !== previousServerValue
            ) {
              nextDraft[item.key] = currentDraft;
            } else {
              nextDraft[item.key] = item.value;
            }
            continue;
          }

          if (preserveDirty) {
            const previousServerValue = previousServerMap[item.key]?.value;
            const hasDraft = prevDraft[item.key] !== undefined;
            const wasDirty = hasDraft && prevDraft[item.key] !== previousServerValue;
            nextDraft[item.key] = wasDirty ? prevDraft[item.key] : item.value;
            continue;
          }

          nextDraft[item.key] = item.value;
        }
        return nextDraft;
      });

      const defaultCategory = sorted[0]?.schema?.category || 'base';
      const currentCategory = activeCategoryRef.current;
      const categoryExists = sorted.some((item) => item.schema?.category === currentCategory);
      const resolvedCategory = categoryExists ? currentCategory : defaultCategory;

      const subs = getSubCategories(resolvedCategory);
      let resolvedSub = activeSubCategoryRef.current;
      if (!subs) {
        resolvedSub = null;
      } else if (
        resolvedCategory !== currentCategory ||
        !resolvedSub ||
        !subs.some((sub) => sub.id === resolvedSub)
      ) {
        resolvedSub = subs[0]?.id ?? null;
      }

      activeCategoryRef.current = resolvedCategory;
      activeSubCategoryRef.current = resolvedSub;
      setActiveCategory(resolvedCategory);
      setActiveSubCategory(resolvedSub);
      setValidationIssues([]);
    },
    [],
  );

  const beginServerSnapshotRequest = useCallback(() => {
    serverSnapshotEpochRef.current += 1;
    return serverSnapshotEpochRef.current;
  }, []);

  const applyServerSnapshot = useCallback((
    snapshot: SystemConfigResponse,
    epoch: number,
    options?: {
      preserveDirty?: boolean;
      committedKeys?: string[];
      committedValues?: Record<string, string>;
    },
  ): boolean => {
    if (serverSnapshotEpochRef.current !== epoch) {
      return false;
    }
    applyServerPayload(snapshot.items, snapshot.configVersion, snapshot.maskToken, {
      ...options,
      configuredNotificationChannels: snapshot.configuredNotificationChannels ?? null,
    });
    return true;
  }, [applyServerPayload]);

  const refreshCommittedSnapshot = useCallback(async (
    committedKeys: string[],
    committedValues?: Record<string, string>,
  ): Promise<void> => {
    const snapshotEpoch = beginServerSnapshotRequest();
    try {
      const refreshed = await systemConfigApi.getConfig(true);
      applyServerSnapshot(refreshed, snapshotEpoch, {
        preserveDirty: true,
        committedKeys,
        committedValues,
      });
    } catch (error: unknown) {
      // The update POST already committed. If a newer load/refresh owns server
      // state now, this obsolete refresh failure must not turn that committed
      // save into a UI error. A failure of the current refresh keeps the
      // existing save-failed/retry behavior.
      if (serverSnapshotEpochRef.current !== snapshotEpoch) {
        return;
      }
      throw error;
    }
  }, [applyServerSnapshot, beginServerSnapshotRequest]);

  const load = useCallback(async (): Promise<boolean> => {
    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;
    const snapshotEpoch = beginServerSnapshotRequest();
    setIsLoading(true);
    setLoadError(null);
    setRetryAction(null);

    try {
      const config = await systemConfigApi.getConfig(true);
      if (loadRequestIdRef.current !== requestId) {
        return false;
      }
      if (!applyServerSnapshot(config, snapshotEpoch)) {
        return false;
      }
      setConflictState(null);
      setToast(null);
      return true;
    } catch (error: unknown) {
      if (
        loadRequestIdRef.current !== requestId
        || serverSnapshotEpochRef.current !== snapshotEpoch
      ) {
        return false;
      }
      setLoadError(getParsedApiError(error));
      setRetryAction('load');
      return false;
    } finally {
      if (loadRequestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  }, [applyServerSnapshot, beginServerSnapshotRequest]);

  const resetDraft = useCallback(() => {
    const next: Record<string, string> = {};
    for (const item of serverItems) {
      next[item.key] = item.value;
    }
    setDraftValues(next);
    setValidationIssues([]);
    setSaveError(null);
    setConflictState(null);
  }, [serverItems]);

  const resetDraftKeys = useCallback((keys: string[]) => {
    const keySet = new Set(keys.map((key) => key.toUpperCase()));
    setDraftValues((previous) => {
      const next = { ...previous };
      for (const key of keySet) {
        const item = serverItemByKeyRef.current[key];
        if (item) {
          next[key] = item.value;
        }
      }
      return next;
    });
    setValidationIssues((previous) => previous.filter((issue) => !keySet.has(issue.key.toUpperCase())));
    setConflictState((previous) => {
      if (!previous) {
        return previous;
      }
      const fields = previous.fields.filter((field) => !keySet.has(field.key.toUpperCase()));
      return fields.length > 0 ? { ...previous, fields } : null;
    });
    setSaveError(null);
  }, []);

  const applyPartialUpdate = useCallback((updatedItems: Array<{ key: string; value: string }>) => {
    setDraftValues((prevDraft) => {
      const nextDraft = { ...prevDraft };
      for (const item of updatedItems) {
        nextDraft[item.key] = item.value;
      }
      return nextDraft;
    });
  }, []);

  const refreshAfterExternalSave = useCallback(
    async (committedKeys: string[]) => {
      await refreshCommittedSnapshot(committedKeys);
    },
    [refreshCommittedSnapshot],
  );

  const setDraftValue = useCallback((key: string, value: string) => {
    setDraftValues((previous) => ({
      ...previous,
      [key]: value,
    }));
  }, []);

  const selectCategory = useCallback((category: string) => {
    const sub = getDefaultSubCategory(category);
    activeCategoryRef.current = category;
    activeSubCategoryRef.current = sub;
    setActiveCategory(category);
    setActiveSubCategory(sub);
  }, []);

  const selectSubCategory = useCallback((sub: string) => {
    activeSubCategoryRef.current = sub;
    setActiveSubCategory(sub);
  }, []);

  const selectTab = useCallback((category: string, sub: string | null) => {
    activeCategoryRef.current = category;
    activeSubCategoryRef.current = sub;
    setActiveCategory(category);
    setActiveSubCategory(sub);
  }, []);

  const getChangedItems = useCallback((): SystemConfigUpdateItem[] => {
    return dirtyKeys
      .map((key) => {
        const serverItem = serverItemByKey[key];
        const normalizedValue = normalizeFieldValue(draftValues[key] ?? '', serverItem?.schema);
        return {
          key,
          value: normalizedValue,
        };
      })
      .filter((item) => {
        const serverItem = serverItemByKey[item.key];
        const normalizedCurrent = normalizeFieldValue(serverItem?.value ?? '', serverItem?.schema);
        return item.value !== normalizedCurrent;
      });
  }, [dirtyKeys, draftValues, serverItemByKey]);

  // On a 409, re-fetch the latest snapshot and compute a field-level three-way
  // diff for the keys we tried to save. Keys the server left unchanged (or that
  // already converged) are not conflicts and can be replayed; the rest surface
  // to the UI so neither side is clobbered by default.
  const buildConflictState = useCallback(
    async (submittedItems: SystemConfigUpdateItem[]): Promise<ConfigConflictState> => {
      const baseByKey = serverItemByKeyRef.current;
      const snapshotEpoch = beginServerSnapshotRequest();
      const latest = await systemConfigApi.getConfig(true);
      if (serverSnapshotEpochRef.current !== snapshotEpoch) {
        throw new Error('Server snapshot request was superseded');
      }
      const latestByKey = new Map(latest.items.map((item) => [item.key, item]));
      const conflictFields: ConfigConflictField[] = [];
      for (const submitted of submittedItems) {
        const baseItem = baseByKey[submitted.key];
        const base = baseItem?.value ?? '';
        const serverItem = latestByKey.get(submitted.key);
        const server = serverItem?.value ?? '';
        const local = submitted.value;
        const schema = serverItem?.schema ?? baseItem?.schema;
        const isSensitive = Boolean(serverItem?.isMasked || baseItem?.isMasked || schema?.isSensitive);
        // Masked snapshots carry no value identity. On any 409, a submitted
        // secret must be resolved explicitly because `****** === ******`
        // cannot prove that another session left the stored secret unchanged.
        if (!isSensitive) {
          if (server === base) {
            continue; // server did not touch this key -> safe to replay
          }
          if (local === server) {
            continue; // both sides converged on the same value
          }
        }
        conflictFields.push({
          key: submitted.key,
          base,
          server,
          local,
          isSensitive,
          title: schema?.title,
          category: schema?.category,
        });
      }
      // Adopt the latest snapshot as the new base while preserving pending local
      // drafts (dirty keys stay editable; server-only changes are absorbed).
      applyServerSnapshot(latest, snapshotEpoch, {
        preserveDirty: true,
      });
      return { fields: conflictFields, serverVersion: latest.configVersion };
    },
    [applyServerSnapshot, beginServerSnapshotRequest],
  );

  const runSave = useCallback(async (
    changedItems?: SystemConfigUpdateItem[],
    options?: { silent?: boolean },
  ): Promise<SaveResult> => {
    const silent = options?.silent ?? false;
    const explicitItems = changedItems ?? [];
    const resolvedChangedItems = explicitItems.length > 0 ? explicitItems : getChangedItems();

    if (!explicitItems.length && !hasDirty) {
      if (!silent) {
        setToast({ type: 'success', message: t('settings.noChangesToSave') });
      }
      return { success: true, message: t('settings.noChangesToSave') };
    }

    if (!resolvedChangedItems.length) {
      if (!silent) {
        setToast({ type: 'success', message: t('settings.noChangesToSave') });
      }
      return { success: true, message: t('settings.noChangesToSave') };
    }

    setIsSaving(true);
    setSaveError(null);
    setRetryAction(null);

    const committedValues: Record<string, string> = {};
    for (const item of resolvedChangedItems) {
      committedValues[item.key] = item.value;
    }

    try {
      const validateResult = await systemConfigApi.validate({ items: resolvedChangedItems });
      setValidationIssues(validateResult.issues || []);

      if (!validateResult.valid) {
        setSaveError(createParsedApiError({
          title: t('settings.validationFailedTitle'),
          message: t('settings.validationFailedMessage'),
          rawMessage: `${t('settings.validationFailedTitle')}: ${t('settings.validationFailedMessage')}`,
          category: 'http_error',
        }));
        setRetryAction('save');
        return {
          success: false,
          message: t('settings.validationFailedTitle'),
          issues: validateResult.issues,
        };
      }

      const updateResult = await systemConfigApi.update({
        configVersion,
        maskToken,
        reloadNow: true,
        items: resolvedChangedItems,
      });

      // Only clear drafts for the keys we just committed; preserve any other
      // pending edits (e.g. sensitive/excluded keys saved manually, or fields
      // edited while this save was in flight — see committedValues).
      await refreshCommittedSnapshot(
        resolvedChangedItems.map((item) => item.key),
        committedValues,
      );
      setConflictState(null);

      if (!silent) {
        setToast({
          type: 'success',
          message: updateResult.warnings?.length
            ? t('settings.configUpdatedWithWarnings', { warnings: updateResult.warnings.join('; ') })
            : t('settings.configUpdated'),
        });
      }
      return { success: true };
    } catch (error: unknown) {
      if (error instanceof SystemConfigValidationError) {
        setValidationIssues(error.issues);
        setSaveError(error.parsedError);
        if (!silent) {
          setToast({ type: 'error', error: getParsedApiError(error) });
        }
        setRetryAction('save');
        return { success: false, message: t('settings.saveFailed') };
      }

      if (error instanceof SystemConfigConflictError) {
        try {
          const nextConflict = await buildConflictState(resolvedChangedItems);
          if (nextConflict.fields.length === 0) {
            // The server changed only unrelated fields. Replay this exact
            // transaction once against the newly adopted version instead of
            // forcing the user through a conflict panel with no conflicts.
            const rebasedResult = await systemConfigApi.update({
              configVersion: nextConflict.serverVersion,
              maskToken,
              reloadNow: true,
              items: resolvedChangedItems,
            });
            await refreshCommittedSnapshot(
              resolvedChangedItems.map((item) => item.key),
              committedValues,
            );
            setConflictState(null);
            if (!silent) {
              setToast({
                type: 'success',
                message: rebasedResult.warnings?.length
                  ? t('settings.configUpdatedWithWarnings', { warnings: rebasedResult.warnings.join('; ') })
                  : t('settings.configUpdated'),
              });
            }
            return { success: true };
          }
          setConflictState(nextConflict);
        } catch {
          // If the refresh fails we cannot compute a diff; leave the draft intact
          // and surface a plain conflict error so the user can reload manually.
          setConflictState(null);
        }
        setSaveError(createParsedApiError({
          title: SETTINGS_PAGE_TEXT[language].conflictTitle,
          message: SETTINGS_PAGE_TEXT[language].conflictDescription,
          rawMessage: error.parsedError.rawMessage,
          status: error.parsedError.status,
          category: error.parsedError.category,
        }));
        // Do not offer a blind retry; the user must resolve conflicts first.
        setRetryAction(null);
        if (!silent) {
          setToast({ type: 'error', error: getParsedApiError(error) });
        }
        return { success: false, message: 'config_conflict' };
      }

      setSaveError(getParsedApiError(error));
      if (!silent) {
        setToast({ type: 'error', error: getParsedApiError(error) });
      }
      setRetryAction('save');
      return { success: false, message: t('settings.saveFailed') };
    } finally {
      setIsSaving(false);
    }
  }, [
    buildConflictState,
    configVersion,
    getChangedItems,
    hasDirty,
    maskToken,
    refreshCommittedSnapshot,
    language,
    t,
  ]);

  // Serialize writes: a second save() while one is in flight reuses the pending
  // promise instead of firing a concurrent, stale-version transaction.
  const save = useCallback((
    changedItems?: SystemConfigUpdateItem[],
    options?: { silent?: boolean },
  ): Promise<SaveResult> => {
    if (savePromiseRef.current) {
      return savePromiseRef.current;
    }
    const promise = runSave(changedItems, options);
    savePromiseRef.current = promise;
    void promise.finally(() => {
      savePromiseRef.current = null;
    });
    return promise;
  }, [runSave]);

  // Resolve one conflicting field: "server" adopts the server value into the
  // draft (dropping the local edit); "local" keeps the pending edit so the next
  // save applies it over the now-current base.
  const resolveConflictField = useCallback((key: string, choice: 'server' | 'local') => {
    const field = conflictState?.fields.find((entry) => entry.key === key);
    if (!field || !conflictState) {
      return;
    }
    if (choice === 'server') {
      setDraftValues((prev) => ({ ...prev, [key]: field.server }));
    }
    const remaining = conflictState.fields.filter((entry) => entry.key !== key);
    setConflictState(remaining.length > 0 ? { ...conflictState, fields: remaining } : null);
    if (remaining.length === 0) {
      setSaveError(null);
    }
  }, [conflictState]);

  const resolveAllConflicts = useCallback((choice: 'server' | 'local') => {
    if (choice === 'server' && conflictState) {
      setDraftValues((prev) => {
        const next = { ...prev };
        for (const field of conflictState.fields) {
          next[field.key] = field.server;
        }
        return next;
      });
    }
    setConflictState(null);
    setSaveError(null);
  }, [conflictState]);

  const dismissConflicts = useCallback(() => {
    setConflictState(null);
    setSaveError(null);
  }, []);

  // Editing updates the local draft; Settings groups schedule the actual save
  // and use this retry entry point after a failed autosave.

  const retry = useCallback(async () => {
    if (retryAction === 'load') {
      await load();
      return;
    }
    if (retryAction === 'save') {
      await save();
    }
  }, [load, retryAction, save]);

  const clearToast = useCallback(() => {
    setToast(null);
  }, []);

  return {
    // Server state
    configVersion,
    maskToken,
    serverItems,
    configuredNotificationChannels,
    categories,
    itemsByCategory,
    issueByKey,

    // UI state
    activeCategory,
    activeSubCategory,
    selectCategory,
    selectSubCategory,
    selectTab,
    hasDirty,
    dirtyKeys,
    dirtyCount: dirtyKeys.length,
    toast,
    clearToast,

    // Request state
    isLoading,
    isSaving,
    loadError,
    saveError,
    retryAction,

    // Conflict state (409 three-way)
    conflictState,
    resolveConflictField,
    resolveAllConflicts,
    dismissConflicts,

    // Actions
    load,
    retry,
    save,
    resetDraft,
    resetDraftKeys,
    setDraftValue,
    getChangedItems,
    applyPartialUpdate,
    refreshAfterExternalSave,
  };
}
