/**
 * Host UI kit — the STUB both harnesses render the panel against.
 *
 * Why a stub: `desktop/plugin.js` is loaded by the app, not by a bundler, so `@hermes/plugin-sdk`
 * exists only inside Hermes. `render_check.mjs` and `preview.mjs` rewrite the panel's one SDK
 * import to their own stub module, and this file is what those stubs re-export (`export * from
 * './kit-stub.mjs'`).
 *
 * What it is NOT: an implementation. Behaviour lives in the app. Two things are mirrored here
 * because the gates depend on them:
 *
 *   1. The DOM contract. `Button`/`RowButton` render a real `<button>`, `Input`/`SearchField` a
 *      real `<input>` (so the harness can type into it and dispatch React's own `input` event),
 *      `PanelMeta` a `<dl>` of `dt`/`dd` pairs, `PanelBlock` a `<pre>`, and `Tip` NOTHING but the
 *      child it wraps — with the label copied onto the child as `data-tip`, which is where the
 *      harness proves the raw check text is still reachable (the app puts the label in a portalled
 *      bubble and never a native `title=`).
 *   2. The VISUAL contract — the class strings are copied verbatim from the kit sources
 *      (`apps/desktop/src/components/ui/*`, `app/overlays/panel.tsx`), and `preview.mjs` embeds the
 *      app's compiled stylesheet, so `shot.cjs` measures the padding/size/grid the app will show.
 *      The stub concatenates classes instead of running `cn()`/tailwind-merge, so only a
 *      conflicting utility (one radius on an icon button) can resolve differently; the gates never
 *      measure that.
 */
import { cloneElement, createContext, createElement as h, useContext } from 'react'

const cx = (...names) => names.filter(Boolean).join(' ')

const BUTTON_BASE =
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 rounded-[2.5px] text-xs leading-4 font-medium whitespace-nowrap shadow-none transition-all duration-100 outline-none focus-visible:border-ring focus-visible:ring-[0.1875rem] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-default disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-3.5"

const BUTTON_VARIANTS = {
  default: 'bg-primary text-primary-foreground hover:bg-primary/90',
  destructive:
    'bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:bg-destructive/60 dark:focus-visible:ring-destructive/40',
  ghost: 'text-(--ui-text-secondary) hover:bg-(--chrome-action-hover) hover:text-(--ui-text-primary)',
  outline:
    'bg-transparent text-(--ui-text-primary) shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--ui-stroke-secondary)_50%,transparent)] hover:bg-(--chrome-action-hover) hover:text-(--ui-text-primary)',
  secondary:
    'bg-(--ui-bg-quaternary) text-(--ui-text-primary) hover:bg-(--chrome-action-hover) hover:text-(--ui-text-primary)'
}

const BUTTON_SIZES = {
  default: 'px-3 py-1.5 has-[>svg]:px-2.5',
  sm: 'px-2.5 py-1 has-[>svg]:px-2',
  icon: 'size-9 rounded-[4px]',
  'icon-xs': "size-6 rounded-[4px] [&_svg:not([class*='size-'])]:size-3",
  'icon-sm': 'size-8 rounded-[4px]'
}

export function Button({ children, className, loading = false, size = 'default', variant = 'default', ...props }) {
  return h('button', {
    type: 'button',
    ...props,
    'aria-busy': loading || undefined,
    className: cx(BUTTON_BASE, BUTTON_VARIANTS[variant], BUTTON_SIZES[size], loading && 'relative', className),
    'data-loading': loading ? '1' : undefined,
    'data-slot': 'button',
    'data-size': size,
    'data-variant': variant
  }, children)
}

// The kit's copy affordance: the payload is resolved INSIDE the component (a string or a function),
// so the stub exposes the resolved text as `data-copy` on the trigger — the same trick `Tip` uses for
// its label — which is where the harness proves the panel hands it the path / the raw check text.
// The kit draws its Copy/Check glyph from the app's own icon set, which this stub does not have: the
// icon-only form carries a placeholder glyph in `size-3.5`, the box the real icon fills, so the
// affordance is visible in the preview instead of rendering as an empty circle.
export function CopyButton({
  appearance = 'button', buttonSize, buttonVariant = 'ghost', className, disabled = false,
  label = 'Copy', showLabel, text
}) {
  const payload = typeof text === 'function' ? '' : String(text ?? '')
  const withLabel = showLabel ?? (appearance !== 'icon' && appearance !== 'tool-row')
  const icon = h('span', { 'aria-hidden': 'true', className: 'size-3.5', 'data-icon': 'copy' },
    withLabel ? null : '⧉')
  return h(Button, {
    'aria-label': label,
    className,
    'data-copy': payload,
    disabled,
    size: buttonSize ?? (appearance === 'icon' ? 'icon' : 'default'),
    variant: buttonVariant
  }, icon, withLabel ? label : null)
}

export function RowButton({ className, type = 'button', ...props }) {
  return h('button', { className, 'data-slot': 'row-button', type, ...props })
}

const BADGE_BASE =
  'inline-flex w-fit shrink-0 items-center gap-1 rounded-[3px] font-medium leading-none whitespace-nowrap [&_svg]:pointer-events-none'

const BADGE_VARIANTS = {
  destructive: 'bg-destructive/10 text-destructive',
  muted: 'bg-muted text-muted-foreground',
  outline: 'border border-(--ui-stroke-secondary) text-muted-foreground',
  success: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-300',
  warn: 'bg-amber-500/10 text-amber-600 dark:text-amber-300'
}

const BADGE_SIZES = {
  default: 'px-1.5 py-0.5 text-[0.65rem] [&_svg]:size-3',
  xs: 'px-1 py-px text-[0.6rem] [&_svg]:size-2.5'
}

export function Badge({ children, className, size = 'default', variant = 'default', ...props }) {
  return h('span', {
    ...props,
    className: cx(BADGE_BASE, BADGE_VARIANTS[variant], BADGE_SIZES[size], className),
    'data-slot': 'badge'
  }, children)
}

export function Tip({ label, children }) {
  return label ? cloneElement(children, { 'data-tip': label }) : children
}

export function Loader({ className, label = 'Loading', type, ...props }) {
  return h('div', {
    ...props,
    'aria-label': props['aria-label'] ?? label,
    className: cx('inline-grid size-10 place-items-center text-primary', className),
    'data-loader': type,
    'data-slot': 'loader',
    role: 'status'
  })
}

export function EmptyState({ className, description, title }) {
  return h('div', { className: cx('grid min-h-48 place-items-center text-center', className) },
    h('div', null,
      h('div', { className: 'text-sm font-medium' }, title),
      description ? h('div', { className: 'mt-1 text-xs text-muted-foreground' }, description) : null))
}

export function ErrorState({ children, className, description, icon, title }) {
  return h('div', { className: cx('grid gap-5', className), 'data-slot': 'error-state' },
    h('div', { className: 'flex flex-col items-center gap-3 text-center' },
      icon ?? h('span', { className: 'text-destructive', 'data-icon': 'error' }),
      typeof title === 'string' ? h('h2', { className: 'text-center text-xl font-semibold tracking-tight' }, title) : title,
      typeof description === 'string'
        ? h('p', { className: 'max-w-prose text-center text-sm leading-5 text-muted-foreground' }, description)
        : description),
    children && h('div', { className: 'grid gap-2' }, children))
}

export function PanelSectionLabel({ children, className }) {
  return h('div', {
    className: cx('text-[0.6rem] font-medium uppercase tracking-wider text-muted-foreground/50', className),
    'data-slot': 'panel-section-label'
  }, children)
}

export function PanelMeta({ className, rows }) {
  return h('dl', { className: cx('grid grid-cols-[5rem_1fr] gap-x-2 gap-y-1 text-[0.7rem]', className),
    'data-slot': 'panel-meta' },
    rows.map((row, index) => h('div', { className: 'contents', key: typeof row.label === 'string' ? row.label : index },
      h('dt', { className: 'truncate text-muted-foreground/55' }, row.label),
      h('dd', { className: 'min-w-0 break-words text-foreground/85' }, row.value))))
}

export function PanelBlock({ children, className }) {
  return h('pre', {
    className: cx('max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-foreground/5 p-2.5 text-[0.68rem] leading-relaxed text-foreground/80', className),
    'data-slot': 'panel-block'
  }, children)
}

export function PanelEmpty({ action, className, description, icon, title }) {
  return h('div', { className: cx('grid flex-1 place-items-center px-6 py-10 text-center', className),
    'data-slot': 'panel-empty' },
    h('div', { className: 'flex flex-col items-center gap-2' },
      h('span', { className: 'text-muted-foreground/50', 'data-icon': icon }),
      title ? h('p', { className: 'text-sm font-medium text-foreground/90' }, title) : null,
      description ? h('p', { className: 'max-w-sm text-xs leading-relaxed text-muted-foreground/70' }, description) : null,
      action ? h('div', { className: 'mt-2' }, action) : null))
}

const CONTROL =
  'desktop-input-chrome w-full min-w-0 rounded-[2.5px] border text-xs leading-4 text-foreground outline-none placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50'

const CONTROL_SIZES = { sm: 'px-2 py-1', xs: 'px-2 py-0.5 text-[0.6875rem] leading-4', default: 'px-2.5 py-1.5' }

// `Input` hands its React event straight through (it IS the native input); `SearchField` hands the
// VALUE, like the kit does. Getting that backwards silently froze the root draft field.
export function Input({ className, onChange, size = 'default', value, ...props }) {
  return h('input', {
    ...props,
    autoComplete: 'off',
    className: cx(CONTROL, CONTROL_SIZES[size], className),
    'data-slot': 'input',
    onChange,
    spellCheck: false,
    value: value ?? ''
  })
}

export function SearchField({
  'aria-label': ariaLabel, containerClassName, hints, inputClassName, onChange, placeholder, value
}) {
  const shown = hints?.length ? hints[0] : placeholder
  return h('div', {
    className: cx('inline-flex min-w-0 max-w-full items-center gap-1.5 border-b border-transparent px-0.5'
      + ' transition-[color,border-color,opacity]' + (value ? '' : ' opacity-30 focus-within:opacity-100'),
    containerClassName)
  },
  h('svg', { 'aria-hidden': 'true', className: 'pointer-events-none size-3.5 shrink-0 text-muted-foreground/70',
    'data-icon': 'search', fill: 'none', stroke: 'currentColor', strokeLinecap: 'round', strokeWidth: 2,
    viewBox: '0 0 24 24' },
  h('circle', { cx: 11, cy: 11, r: 7 }), h('path', { d: 'm20 20-3.5-3.5' })),
  h('input', {
    'aria-label': ariaLabel ?? placeholder,
    className: cx('h-7 min-w-0 max-w-full bg-transparent text-xs text-foreground placeholder:text-muted-foreground focus:outline-none', inputClassName),
    onChange: event => onChange(event.target.value),
    placeholder: shown,
    type: 'text',
    value
  }))
}

export function SegmentedControl({ className, disabled = false, onChange, options, value }) {
  return h('div', {
    className: cx('inline-grid w-fit auto-cols-fr grid-flow-col gap-0.5 rounded-[5px] bg-(--ui-bg-tertiary) p-0.5',
      disabled && 'opacity-50', className),
    'data-slot': 'segmented-control',
    role: 'group'
  }, options.map(option => h('button', {
    'aria-pressed': value === option.id,
    className: cx('flex items-center justify-center gap-1 rounded-[3px] px-2.5 py-0.5 text-[0.6875rem] font-medium transition-colors',
      value === option.id ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'),
    disabled,
    key: option.id,
    onClick: () => onChange(option.id),
    type: 'button'
  }, option.label)))
}

/**
 * The host's confirmation dialog, stubbed for the harness. The REAL one is portalled, focuses Confirm,
 * takes Enter/Esc, and keeps itself open when `onConfirm` throws — none of which a screenshot can show.
 * What this mirrors is the CONTENT the gate can measure: the title, the description, the children and
 * the two buttons with the kit's own classes (so the destructive pair is the app's, not the panel's),
 * laid out like the kit's Dialog: a dimmed backdrop over the page and a centred max-w-md panel.
 */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false
}) {
  if (!open) return null
  return h('div', { className: 'cd-root', 'data-slot': 'confirm-dialog', style: {
    position: 'fixed', inset: '0', zIndex: '50', display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'rgba(0, 0, 0, 0.5)', padding: '16px' } },
    h('div', {
      className: cx('cd-panel', destructive && 'cd-destructive'),
      role: 'dialog',
      'aria-modal': 'true',
      style: {
        border: '1px solid ' + (destructive ? 'var(--ui-orange)' : 'var(--ui-stroke-primary)'),
        borderRadius: '12px',
        background: 'var(--ui-bg-tertiary)',
        padding: '20px 22px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        width: '100%',
        maxWidth: '448px'
      }
    },
    h('div', { className: 'cd-title', style: { fontSize: '15px', fontWeight: '600' } }, title),
    description ? h('div', { className: 'cd-desc' }, description) : null,
    children || null,
    h('div', { className: 'cd-actions', style: { display: 'flex', gap: '8px', justifyContent: 'flex-end' } },
      h('button', {
        type: 'button',
        className: cx(BUTTON_BASE, BUTTON_VARIANTS.outline, BUTTON_SIZES.sm),
        'data-slot': 'confirm-cancel',
        onClick: onClose
      }, cancelLabel),
      h('button', {
        type: 'button',
        className: cx(BUTTON_BASE, destructive ? BUTTON_VARIANTS.destructive : BUTTON_VARIANTS.default,
          BUTTON_SIZES.sm),
        'data-slot': 'confirm-confirm',
        onClick: onConfirm
      }, confirmLabel))))
}

// The Health tab (the former Wiki Watchdog panel) builds on three more kit surfaces: the list/row/detail
// trio of `app/overlays/panel.tsx`. Class strings are copied from there, like everything above.
export function PanelList({ children, className, onSearchChange, searchLabel, searchPlaceholder, searchValue }) {
  return h('div', {
    className: cx('flex w-full shrink-0 flex-col max-[47.5rem]:max-h-[40%] min-[47.5rem]:w-52', className),
    'data-slot': 'panel-list'
  },
  onSearchChange
    ? h('input', {
        'aria-label': searchLabel ?? searchPlaceholder ?? '',
        className: 'mb-1 w-full shrink-0 border-b border-(--ui-stroke-tertiary) bg-transparent text-xs outline-none',
        onChange: e => onSearchChange(e.target.value),
        placeholder: searchPlaceholder ?? '',
        value: searchValue ?? ''
      })
    : null,
  h('div', { className: 'flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain' }, children))
}

export function PanelListRow({ active, dotClassName, icon, lead, menu, meta, onSelect, rowKey, title }) {
  return h('div', {
    className: cx('group/row row-hover relative flex h-7 w-full items-center rounded-md text-[0.78rem] hover:text-foreground',
      active ? 'bg-(--ui-row-active-background) text-foreground' : 'text-(--ui-text-secondary)'),
    'data-panel-row': rowKey,
    'data-slot': 'panel-list-row'
  },
  h('button', {
    className: 'flex h-full min-w-0 flex-1 items-center gap-2 rounded-md pl-2 pr-1 text-left',
    'data-slot': 'row-button',
    onClick: onSelect,
    type: 'button'
  },
  lead ?? (dotClassName
    ? h('span', { 'aria-hidden': 'true', className: cx('size-1.5 shrink-0 rounded-full', dotClassName) })
    : icon ? h('span', { 'aria-hidden': 'true', className: 'shrink-0 text-muted-foreground/55', 'data-icon': icon })
      : null),
  h('span', { className: 'min-w-0 flex-1 truncate font-medium text-foreground/85' }, title)),
  meta ? h('span', { className: 'shrink-0 pr-2 text-[0.62rem] tabular-nums text-muted-foreground/45' }, meta) : null,
  menu ? h('div', { className: 'shrink-0 pr-1' }, menu) : null)
}

export function PanelDetail({ children, className }) {
  return h('div', {
    className: cx('min-h-0 flex-1 overflow-y-auto overscroll-contain', className),
    'data-slot': 'panel-detail'
  }, h('div', { className: 'space-y-4 pb-6 pl-1 pr-2' }, children))
}

// The kit's Tabs (`components/ui/tabs.tsx`, Radix underneath). The stub keeps the DOM contract the
// gates read: a `tablist` of `tab` buttons carrying `aria-selected` and `data-state`, and the value
// handed back through `onValueChange` on click, as Radix does.
const TabsCtx = createContext({ value: undefined, onValueChange: () => {} })

export function Tabs({ children, className, onValueChange, value, ...props }) {
  return h(TabsCtx.Provider, { value: { value, onValueChange: onValueChange || (() => {}) } },
    h('div', { ...props, className: cx('flex flex-col gap-2', className), 'data-slot': 'tabs' }, children))
}

export function TabsList({ children, className, ...props }) {
  return h('div', {
    ...props,
    className: cx('inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground', className),
    'data-slot': 'tabs-list',
    role: 'tablist'
  }, children)
}

export function TabsTrigger({ children, className, value, ...props }) {
  const ctx = useContext(TabsCtx)
  const on = ctx.value === value
  return h('button', {
    ...props,
    'aria-selected': on ? 'true' : 'false',
    className: cx('inline-flex h-7 items-center justify-center gap-1.5 rounded-md px-3 text-sm font-medium '
      + 'whitespace-nowrap transition-all outline-none focus-visible:bg-background focus-visible:text-foreground '
      + 'focus-visible:ring-[0.1875rem] focus-visible:ring-ring/35 disabled:pointer-events-none disabled:opacity-50 '
      + 'data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-xs', className),
    'data-slot': 'tabs-trigger',
    'data-state': on ? 'active' : 'inactive',
    'data-value': value,
    onClick: () => ctx.onValueChange(value),
    role: 'tab',
    type: 'button'
  }, children)
}
