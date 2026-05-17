# UI primitives (Pawrrtal)

Canonical behavior and tokens live in repo-root **`DESIGN.md`**. This folder holds shadcn-style building blocks plus **Pawrrtal shells** over vendored packages.

## Responsive overlays

| Export | Role |
| --- | --- |
| **`AppDialog`** (`app-dialog.tsx`) | **Use this in feature code.** Centered `Modal` on wide viewports, `BottomSheet` below 768px (`useIsMobile`). Compose **`header`** / **`footer`** / body **`children`** with **`ModalHeader`**, **`ModalDescription`**, etc. from **`@octavian-tocan/react-overlay`** so mobile gets sticky chrome. Optional **`sheetTitle`** for sheet aria. Prefer **`AppDialogFooter`** in **`footer`** for stacked mobile actions. |
| **`ResponsiveModal`** (`responsive-modal.tsx`) | Implementation layer (portal + Modal/BottomSheet split). Prefer **`AppDialog`** unless you are extending shared UI plumbing. |

Do **not** import shadcn **`dialog`**, **`alert-dialog`**, or **`sheet`** into features for product modals — see **`.claude/rules/react/use-octavian-overlay-for-modals.md`**.

## Empty states & dialog scaffolding

| Export | Role |
| --- | --- |
| **`AppEmptyState`** (`app-empty-state.tsx`) | Shared empty placeholders (`tone`: sidebar / page / card / panel; optional **`layout="inlineCta"`**). Feature wrappers stay thin. |
| **`AppFormRow`** (`app-form-row.tsx`) | Dialog-sized label + helper + error slot (`AppDialog` bodies). Full-page forms may still use **`Field`**. |
| **`AppDialogCallout`** (`app-dialog-callout.tsx`) | Info/warning strips inside dialogs (`tone`: info / warning). |
| **`AppDialogFooter`** (`app-dialog-footer.tsx`) | Modal footer stack (`flex-col-reverse` narrow → row **`sm:`**); optional **`align`**. |

## Sidebar primitives

| Export | Role |
| --- | --- |
| **`SidebarNavRow`** (`sidebar-nav-row.tsx`) | Hover/selected chrome + density split for sidebar lists. **`entity-row`** / **`ProjectRow`** / Tasks **`NavRow`** compose this. |
| **`SidebarSectionHeader`** (`sidebar-section-header.tsx`) | Collapsible group headers (chevron + meta + **`trailingSlot`**) or static uppercase labels; owns floating hover tray. |

## Chips & metadata

| Export | Role |
| --- | --- |
| **`AppPill`** (`app-pill.tsx`) | Semantic status pills (`tone` + **`shape`**: pill vs tag). Replaces ad hoc emerald/amber badge classes in integrations, Knowledge counts, task **`TagChip`**. |

## Menus and panels

Panel-style dropdowns use **`@octavian-tocan/react-dropdown`** (vendored under **`frontend/lib/react-dropdown`**). **`DropdownMenuProvider`** / menu wiring may appear via **`menu-context.tsx`** and feature rows (e.g. **`entity-row.tsx`**). Scanning and disabled-row rules are documented under **Menu primitives** in **`DESIGN.md`**.

## Everything else

Buttons, inputs, **`sidebar`**, **`card`**, etc. follow the Craft Agents tokens in **`frontend/app/globals.css`** / **`DESIGN.md`**.
