# jclee-bot Design System

## 1. Atmosphere & Identity

jclee-bot UI surfaces are operational command centers for automation evidence. The feel is precise, dark, and instrumented: a quiet console where logs, checks, and health signals can be scanned quickly without marketing treatment. The signature is a thin violet evidence rail paired with compact status cards and monospaced command artifacts.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/primary | `--surface-primary` | `#f7f8f8` | `#08090a` | Page background |
| Surface/secondary | `--surface-secondary` | `#ffffff` | `#0f1011` | Panels |
| Surface/elevated | `--surface-elevated` | `#f3f4f5` | `#191a1b` | Cards and command blocks |
| Text/primary | `--text-primary` | `#101113` | `#f7f8f8` | Headings and primary body |
| Text/secondary | `--text-secondary` | `#525967` | `#d0d6e0` | Supporting copy |
| Text/tertiary | `--text-tertiary` | `#69717d` | `#8a8f98` | Metadata and helper text |
| Border/default | `--border-default` | `#d0d7de` | `rgba(255,255,255,0.08)` | Cards and controls |
| Border/subtle | `--border-subtle` | `#e6e8eb` | `rgba(255,255,255,0.05)` | Dividers |
| Accent/primary | `--accent-primary` | `#5e6ad2` | `#7170ff` | Primary action and focus |
| Accent/hover | `--accent-hover` | `#4651c7` | `#828fff` | Hover and active action |
| Status/success | `--status-success` | `#16833a` | `#27a644` | Healthy checks |
| Status/warning | `--status-warning` | `#b7791f` | `#d99a2b` | Missing or stale evidence |
| Status/error | `--status-error` | `#c53030` | `#f05252` | Failed checks |
| Status/info | `--status-info` | `#2563eb` | `#6ea8fe` | Neutral runtime information |

### Rules

- Use the violet accent only for actions, focus, and the evidence rail.
- Use status colors only for health outcomes.
- Do not introduce infrastructure-specific host colors or secret-bearing labels.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| Display | `48px` | 590 | 1.05 | 0 | Demo page title |
| H1 | `36px` | 590 | 1.15 | 0 | Major page headings |
| H2 | `24px` | 590 | 1.25 | 0 | Section headings |
| H3 | `18px` | 590 | 1.35 | 0 | Card titles |
| Body/lg | `18px` | 400 | 1.6 | 0 | Lead copy |
| Body | `16px` | 400 | 1.6 | 0 | Default text |
| Body/sm | `14px` | 400 | 1.5 | 0 | Helper text |
| Caption | `12px` | 510 | 1.4 | 0 | Labels and metadata |
| Mono | `13px` | 400 | 1.5 | 0 | Commands and JSON |

### Font Stack

- Primary: `Inter Variable, SF Pro Display, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif`
- Mono: `Berkeley Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`

### Rules

- Letter spacing is 0 to preserve Korean readability.
- Monospace appears only for endpoints, commands, JSON, and log-like evidence.

## 4. Spacing & Layout

### Base Unit

All spacing derives from 4px.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | `4px` | Tight inline gaps |
| `--space-2` | `8px` | Labels and compact controls |
| `--space-3` | `12px` | Field padding |
| `--space-4` | `16px` | Card inner rhythm |
| `--space-5` | `20px` | Panel padding |
| `--space-6` | `24px` | Standard section gap |
| `--space-8` | `32px` | Grid gap |
| `--space-10` | `40px` | Page section gap |
| `--space-12` | `48px` | Major vertical rhythm |
| `--space-16` | `64px` | Hero spacing |

### Grid

- Max content width: `1180px`
- Column system: responsive 12-column grid with dense cards on desktop and single-column mobile flow.
- Breakpoints: `640px`, `768px`, `1024px`, `1280px`.

### Rules

- Demo pages should reveal the key evidence action in the first viewport.
- Cards stay at `8px` radius unless a large hero panel needs `12px`.

## 5. Components

### Evidence Demo Shell
- **Structure**: Header, status rail, control panel, evidence output grid, command block.
- **Variants**: live check, pasted JSON, sample response.
- **Spacing**: `--space-6` panel padding, `--space-8` grid gap.
- **States**: idle, loading, healthy, critical, error, empty.
- **Accessibility**: semantic sections, labels for all inputs, `aria-live` output status.
- **Motion**: opacity and transform only; disabled when `prefers-reduced-motion` is active.

### Evidence Card
- **Structure**: label, value, supporting copy.
- **Variants**: status, metric, command, note.
- **Spacing**: `--space-4` internal padding.
- **States**: default, hover, warning, error.
- **Accessibility**: status text is never conveyed by color alone.
- **Motion**: subtle translate on hover for pointer devices.

### Action Button
- **Structure**: `button` with text label.
- **Variants**: primary, secondary.
- **Spacing**: `--space-3` vertical, `--space-4` horizontal.
- **States**: default, hover, active, focus, disabled, loading.
- **Accessibility**: visible focus ring and disabled state.
- **Motion**: 140ms transform and background transition.

## 6. Motion & Interaction

### Timing

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | `140ms` | ease-out | Button hover and press |
| Standard | `220ms` | ease-in-out | Evidence panel reveal |
| Emphasis | `420ms` | cubic-bezier(0.16, 1, 0.3, 1) | Hero rail entry |

### Rules

- Animate only `opacity` and `transform`.
- Respect `prefers-reduced-motion` by removing decorative movement.
- Never animate layout dimensions in evidence panels.

## 7. Depth & Surface

### Strategy

Mixed: dark tonal shifts plus subtle borders.

| Level | Value | Usage |
|-------|-------|-------|
| Panel | `1px solid var(--border-default)` | Main containers |
| Subtle | `1px solid var(--border-subtle)` | Dividers |
| Glow | `0 16px 60px rgba(113,112,255,0.14)` | Hero evidence rail only |
