// Single source of truth for overlay stacking order. Higher sits closer to the
// user. Components that set z-index dynamically (the shared Drawer, run-flow and
// report drawers, ConfirmDialog) import from here; the remaining overlays use
// matching Tailwind classes, documented below so the whole scale stays legible:
//
//   pageDrawer    60  Home/Chat mobile history drawers
//   navigation    70  application navigation drawer
//   drawer/modal  80  default content overlays
//   runFlow      100  Home run-flow drawer
//   report       110  report markdown drawer
//   dropdown     140  Select / autocomplete popovers
//   tooltip      160  Tooltip / menus
//   settings     180  Settings help modal
//   confirm      200  destructive/transaction confirmation
//   toast        220  transient global feedback
export const OVERLAY_Z = {
  pageDrawer: 60,
  navigationDrawer: 70,
  drawer: 80,
  modal: 80,
  runFlowDrawer: 100,
  reportDrawer: 110,
  dropdown: 140,
  tooltip: 160,
  settingsModal: 180,
  confirm: 200,
  toast: 220,
} as const;
