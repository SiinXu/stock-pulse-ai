// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { ScreeningRunParameters } from '../components/screening/screeningRunState';
import { readScreeningRunParameters } from '../components/screening/screeningRunState';
import {
  composeScreeningHref,
  readScreeningSelectionFromSearch,
  type ScreeningUrlPatch,
  type ScreeningUrlState,
} from './stockScreeningUrlState';

type UseScreeningUrlStateResult = {
  expandedCode: string | null;
  setExpandedCode: Dispatch<SetStateAction<string | null>>;
  hotspotsExpanded: boolean;
  setHotspotsExpanded: Dispatch<SetStateAction<boolean>>;
  selectedHotspotTopic: string | null;
  setSelectedHotspotTopic: Dispatch<SetStateAction<string | null>>;
  selectedHotspotTopicRef: MutableRefObject<string | null>;
  commitScreeningUrl: (
    selectionPatch: ScreeningUrlPatch,
    runParameters?: ScreeningRunParameters,
    options?: { history?: 'replace' | 'push' },
  ) => void;
  handleExpandedCodeChange: (code: string | null) => void;
  handleHotspotSelect: (topic: string) => void;
  toggleHotspotsExpanded: () => void;
  clearCandidateFromUrl: () => void;
};

export function useScreeningUrlState(
  runParameters: ScreeningRunParameters,
  setRunParameters: {
    setMarket: (market: string) => void;
    setStrategy: (strategy: string) => void;
    setMaxResults: (maxResults: number) => void;
    setMaxResultsDraft: (draft: string) => void;
  },
): UseScreeningUrlStateResult {
  const navigate = useNavigate();
  const location = useLocation();
  const lastWrittenSearchRef = useRef<string | null>(null);
  const hasHydratedSearchRef = useRef(false);
  const [initialSelection] = useState<ScreeningUrlState>(() => (
    readScreeningSelectionFromSearch(
      typeof window === 'undefined' ? '' : window.location.search,
    )
  ));
  const [expandedCode, setExpandedCode] = useState<string | null>(initialSelection.candidate);
  const [hotspotsExpanded, setHotspotsExpanded] = useState(initialSelection.hotspotsOpen);
  const [selectedHotspotTopic, setSelectedHotspotTopic] = useState<string | null>(initialSelection.hotspot);
  const selectedHotspotTopicRef = useRef<string | null>(initialSelection.hotspot);

  const { market, strategy, maxResults } = runParameters;
  const { setMarket, setStrategy, setMaxResults, setMaxResultsDraft } = setRunParameters;

  const commitScreeningUrl = useCallback((
    selectionPatch: ScreeningUrlPatch,
    nextRun: ScreeningRunParameters = { market, strategy, maxResults },
    options: { history?: 'replace' | 'push' } = {},
  ) => {
    const composed = composeScreeningHref(nextRun, selectionPatch, options);
    if (!composed) return;
    lastWrittenSearchRef.current = composed.search;
    navigate(composed.href, { replace: composed.history === 'replace' });
  }, [market, maxResults, navigate, strategy]);

  const selectionSnapshot = useCallback((): ScreeningUrlState => ({
    candidate: expandedCode,
    hotspot: selectedHotspotTopic,
    hotspotsOpen: hotspotsExpanded || Boolean(selectedHotspotTopic),
  }), [expandedCode, hotspotsExpanded, selectedHotspotTopic]);

  useEffect(() => {
    commitScreeningUrl(selectionSnapshot(), { market, strategy, maxResults }, { history: 'replace' });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- filter-driven sync only
  }, [market, maxResults, strategy]);

  useEffect(() => {
    if (lastWrittenSearchRef.current !== null && location.search === lastWrittenSearchRef.current) {
      lastWrittenSearchRef.current = null;
      return;
    }
    const values = readScreeningSelectionFromSearch(location.search);
    setExpandedCode(values.candidate);
    setHotspotsExpanded(values.hotspotsOpen);
    setSelectedHotspotTopic(values.hotspot);
    selectedHotspotTopicRef.current = values.hotspot;
    if (!hasHydratedSearchRef.current) {
      hasHydratedSearchRef.current = true;
      return;
    }
    const next = readScreeningRunParameters(null, location.search);
    setMarket(next.market);
    setStrategy(next.strategy);
    setMaxResults(next.maxResults);
    setMaxResultsDraft(String(next.maxResults));
  }, [location.search, setMarket, setMaxResults, setMaxResultsDraft, setStrategy]);

  const handleExpandedCodeChange = useCallback((code: string | null) => {
    setExpandedCode(code);
    commitScreeningUrl({ candidate: code });
  }, [commitScreeningUrl]);

  const clearCandidateFromUrl = useCallback(() => {
    commitScreeningUrl({ candidate: null });
  }, [commitScreeningUrl]);

  const handleHotspotSelect = useCallback((topic: string) => {
    selectedHotspotTopicRef.current = topic;
    setSelectedHotspotTopic(topic);
    setHotspotsExpanded(true);
    commitScreeningUrl({ hotspot: topic, hotspotsOpen: true });
  }, [commitScreeningUrl]);

  const toggleHotspotsExpanded = useCallback(() => {
    const nextExpanded = !hotspotsExpanded;
    if (!nextExpanded) {
      selectedHotspotTopicRef.current = null;
      setSelectedHotspotTopic(null);
      setHotspotsExpanded(false);
      commitScreeningUrl({ hotspot: null, hotspotsOpen: false });
      return;
    }
    setHotspotsExpanded(true);
    commitScreeningUrl({ hotspotsOpen: true });
  }, [commitScreeningUrl, hotspotsExpanded]);

  return {
    expandedCode,
    setExpandedCode,
    hotspotsExpanded,
    setHotspotsExpanded,
    selectedHotspotTopic,
    setSelectedHotspotTopic,
    selectedHotspotTopicRef,
    commitScreeningUrl,
    handleExpandedCodeChange,
    handleHotspotSelect,
    toggleHotspotsExpanded,
    clearCandidateFromUrl,
  };
}
