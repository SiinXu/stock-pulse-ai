import { useReducer } from 'react';

export type ChatPageUiState = {
  showSkillDesc: string | null;
  mobileSkillPickerOpen: boolean;
  sessionSearch: string;
  expandedThinking: Set<string>;
  deleteConfirmId: string | null;
  deleteLoading: boolean;
  deleteError: string | null;
  sidebarOpen: boolean;
  sending: boolean;
  chatMode: 'chat' | 'research';
  showJumpToBottom: boolean;
};

type ChatPageUiAction =
  | { type: 'setShowSkillDesc'; skillId: string | null }
  | { type: 'setMobileSkillPickerOpen'; open: boolean }
  | { type: 'toggleMobileSkillPicker' }
  | { type: 'setSessionSearch'; value: string }
  | { type: 'toggleThinking'; messageId: string }
  | { type: 'setDeleteConfirmId'; sessionId: string | null }
  | { type: 'setDeleteLoading'; loading: boolean }
  | { type: 'setDeleteError'; error: string | null }
  | { type: 'setSidebarOpen'; open: boolean }
  | { type: 'setSending'; sending: boolean }
  | { type: 'setChatMode'; mode: 'chat' | 'research' }
  | { type: 'setShowJumpToBottom'; show: boolean };

const initialState: ChatPageUiState = {
  showSkillDesc: null,
  mobileSkillPickerOpen: false,
  sessionSearch: '',
  expandedThinking: new Set(),
  deleteConfirmId: null,
  deleteLoading: false,
  deleteError: null,
  sidebarOpen: false,
  sending: false,
  chatMode: 'chat',
  showJumpToBottom: false,
};

function chatPageUiReducer(
  state: ChatPageUiState,
  action: ChatPageUiAction,
): ChatPageUiState {
  switch (action.type) {
    case 'setShowSkillDesc':
      return { ...state, showSkillDesc: action.skillId };
    case 'setMobileSkillPickerOpen':
      return { ...state, mobileSkillPickerOpen: action.open };
    case 'toggleMobileSkillPicker':
      return { ...state, mobileSkillPickerOpen: !state.mobileSkillPickerOpen };
    case 'setSessionSearch':
      return { ...state, sessionSearch: action.value };
    case 'toggleThinking': {
      const next = new Set(state.expandedThinking);
      if (next.has(action.messageId)) next.delete(action.messageId);
      else next.add(action.messageId);
      return { ...state, expandedThinking: next };
    }
    case 'setDeleteConfirmId':
      return { ...state, deleteConfirmId: action.sessionId };
    case 'setDeleteLoading':
      return { ...state, deleteLoading: action.loading };
    case 'setDeleteError':
      return { ...state, deleteError: action.error };
    case 'setSidebarOpen':
      return { ...state, sidebarOpen: action.open };
    case 'setSending':
      return { ...state, sending: action.sending };
    case 'setChatMode':
      return { ...state, chatMode: action.mode };
    case 'setShowJumpToBottom':
      return { ...state, showJumpToBottom: action.show };
    default:
      return state;
  }
}

export function useChatPageUiState() {
  return useReducer(chatPageUiReducer, initialState);
}
