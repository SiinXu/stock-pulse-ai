// Single source of truth for overlay stacking order. Higher sits closer to the
// user. Components that set z-index dynamically (the shared Drawer, run-flow and
// report drawers, ConfirmDialog) import from here; the remaining overlays use
// matching Tailwind classes, documented below so the whole scale stays legible:
//
//   pageDrawer   40   Home/Chat mobile history sidebars
//   drawer       50   shared Drawer default
//   modal        50   centered Modal
//   runFlowDrawer 80  Home run-flow drawer
//   navigationDrawer 90 Shell mobile navigation
//   reportDrawer 100  report markdown drawer
//   dropdown     100  Select / autocomplete popovers
//   tooltip      120  Tooltip / menus
//   settingsModal 140 Settings help modal
//   confirm      200  ConfirmDialog — always above every dismissible surface
export const OVERLAY_Z = {
  pageDrawer: 40,
  drawer: 50,
  modal: 50,
  runFlowDrawer: 80,
  navigationDrawer: 90,
  reportDrawer: 100,
  dropdown: 100,
  tooltip: 120,
  settingsModal: 140,
  confirm: 200,
} as const;
