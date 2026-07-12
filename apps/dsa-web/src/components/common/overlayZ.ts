// Single source of truth for overlay stacking order. Higher sits closer to the
// user. Components that set z-index dynamically (the shared Drawer, run-flow and
// report drawers, ConfirmDialog) import from here; the remaining overlays use
// matching Tailwind classes, documented below so the whole scale stays legible:
//
//   pageDrawer   40   Home/Chat mobile history sidebars      (Tailwind z-40)
//   drawer       50   shared Drawer default / centered Modal (Tailwind z-50)
//   runFlowDrawer 80  Home run-flow drawer
//   confirm      90   ConfirmDialog — always above drawers/modals
//   reportDrawer 100  report markdown drawer
//   dropdown     100  Select / autocomplete popovers         (Tailwind z-[100])
//   tooltip      120  Tooltip / menus                        (Tailwind z-[120])
//   settingsModal 140 Settings help modal                    (Tailwind z-[140])
export const OVERLAY_Z = {
  pageDrawer: 40,
  drawer: 50,
  runFlowDrawer: 80,
  confirm: 90,
  reportDrawer: 100,
  dropdown: 100,
  tooltip: 120,
  settingsModal: 140,
} as const;
