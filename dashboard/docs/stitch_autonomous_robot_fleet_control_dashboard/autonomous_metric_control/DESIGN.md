---
name: Autonomous Metric Control
colors:
  surface: '#E5E7EB'
  surface-dim: '#d3daef'
  surface-bright: '#f9f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f1f3ff'
  surface-container: '#e9edff'
  surface-container-high: '#e1e8fd'
  surface-container-highest: '#dce2f7'
  on-surface: '#141b2b'
  on-surface-variant: '#404941'
  inverse-surface: '#293040'
  inverse-on-surface: '#edf0ff'
  outline: '#717970'
  outline-variant: '#c0c9be'
  surface-tint: '#2e6a41'
  primary: '#003b1b'
  on-primary: '#ffffff'
  primary-container: '#14532d'
  on-primary-container: '#87c695'
  inverse-primary: '#96d5a3'
  secondary: '#006e2d'
  on-secondary: '#ffffff'
  secondary-container: '#7cf994'
  on-secondary-container: '#007230'
  tertiary: '#30322f'
  on-tertiary: '#ffffff'
  tertiary-container: '#464946'
  on-tertiary-container: '#b6b8b3'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#b1f2be'
  primary-fixed-dim: '#96d5a3'
  on-primary-fixed: '#00210d'
  on-primary-fixed-variant: '#12512c'
  secondary-fixed: '#7ffc97'
  secondary-fixed-dim: '#62df7d'
  on-secondary-fixed: '#002109'
  on-secondary-fixed-variant: '#005320'
  tertiary-fixed: '#e2e3de'
  tertiary-fixed-dim: '#c5c7c2'
  on-tertiary-fixed: '#1a1c19'
  on-tertiary-fixed-variant: '#454744'
  background: '#f9f9ff'
  on-background: '#141b2b'
  surface-variant: '#dce2f7'
  accent: '#DCFCE7'
  positive-accent: '#DCFCE7'
  border-grid: '#E2E8F0'
  surface-subtle: '#E5E7EB'
  warning: '#D97706'
  warning-surface: '#FEF3C7'
  critical: '#DC2626'
  critical-surface: '#FEE2E2'
typography:
  headline-lg:
    fontFamily: Gmarket Sans, sans-serif
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
  headline-lg-mobile:
    fontFamily: Gmarket Sans, sans-serif
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
  headline-md:
    fontFamily: Gmarket Sans, sans-serif
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
  headline-sm:
    fontFamily: Gmarket Sans, sans-serif
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 24px
  body-lg:
    fontFamily: Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto,
      sans-serif
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto,
      sans-serif
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto,
      sans-serif
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-caps:
    fontFamily: Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto,
      sans-serif
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.05em
  telemetry-lg:
    fontFamily: JetBrains Mono, monospace
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 28px
  telemetry-md:
    fontFamily: JetBrains Mono, monospace
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 20px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  margin: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system delivers a mission-critical, high-confidence aesthetic tailored for autonomous robotic control dashboards and real-time visitor guidance interfaces. Combining precision data telemetry with approachable public-facing clarity, the visual language balances high-density information architecture with calm authority.

The visual style merges structured modern corporate architecture with high-contrast tactical cues:
- Crisp data segmentation through subtle outlines and clean surface tiers.
- High-visibility status accents to provide immediate cognitive feedback during operation.
- Purposeful contrast balancing deep industrial greens with soft neutral backgrounds to avoid operator fatigue during continuous monitoring.

## Colors

The palette establishes an authoritative tone with deep forest green while ensuring critical operational statuses are unmistakably recognizable across diverse ambient conditions:

- **Primary (`#14532D`)**: Command headers, dominant navigation panels, and core brand anchoring.
- **Secondary (`#16A34A`)**: Active telemetric states, primary action triggers, and operational confirmations.
- **Tertiary (`#F7F8F3`)**: Eye-resting base surface backdrop engineered for prolonged monitor and mobile viewing.
- **Neutral (`#111827`)**: High-contrast typography, metrics readouts, and primary data labels.
- **Functional Semantics**:
  - `positive-accent` (`#DCFCE7`): Normal telemetry reception and healthy device status badges.
  - `warning` (`#D97706` / `#FEF3C7`): Signal latency, low battery alerts, and non-blocking operator warnings.
  - `critical` (`#DC2626` / `#FEE2E2`): E-stop (emergency stop) controls, disconnected nodes, and system faults.

## Typography

The typographic hierarchy is divided into distinct functional roles:
- **Headlines (`Gmarket Sans`)**: Provides structured geometric presence for page titles, modal heads, and primary telemetry section titles. Weights are restricted to `700` (Bold) for high-impact titles and `500` (Medium) for subsection anchors.
- **General Body & UI Text (`Pretendard`)**: Utilized across all functional labels, form fields, table contents, and explanatory copy. Its neo-grotesque geometry ensures legibility on dense dashboards and mobile views.
- **Telemetry Readouts (`JetBrains Mono`)**: Retained for numerical coordinate streams, timestamp logs, speed/battery meters, and sensor telemetry to prevent tabular jitter during live data streams.

## Layout & Spacing

Layouts follow a structured modular grid system optimized for high-density operator dashboards and single-column mobile views:

- **Desktop (1024px+)**: 12-column fluid grid system with `1rem` gutters and `1.5rem` canvas margins. Supports tri-pane monitoring (Robot Map/LiDAR, Live Control & Waypoint Panel, Telemetry & Event Log).
- **Tablet (768px - 1023px)**: 8-column layout with prioritized collapsible tool drawers.
- **Mobile (<768px)**: 4-column single-stack arrangement optimized for visitor location viewing and urgent field operations.

## Elevation & Depth

Visual depth is conveyed through structured tonal layering and crisp, low-contrast ghost borders rather than heavy atmospheric shadows:

- **Base Canvas**: Surface base `#F7F8F3`.
- **Card Tier 1**: Crisp white `#FFFFFF` surface bordered by a 1px solid stroke (`border-grid` `#E2E8F0`).
- **Card Tier 2 (Hover / Elevated Modals)**: Subtle ambient drop shadow (`0 4px 12px rgba(17, 24, 39, 0.05)`) with reinforced contrast border.
- **Critical Overlays**: High-contrast outline treatment with darkened translucent backdrop (`rgba(17, 24, 39, 0.4)`).

## Shapes

The design system employs a soft, precision-engineered corner radius (`roundedness: 1`):
- Default components (inputs, standard buttons, data table cells) use `0.25rem` (4px).
- Surface cards, video/map viewport containers, and modal panels use `rounded-lg` (0.5rem / 8px).
- Badges, status tags, and floating emergency action buttons utilize `rounded-full` (9999px) for clear affordance separation.

## Components

### Buttons
- **Primary Action**: Solid `#14532D` background with `#FFFFFF` text in `Pretendard` weight `600`. Hover shifts subtly to `#16A34A`.
- **Secondary / Ghost**: Transparent fill with 1px border (`#E2E8F0`), `#111827` label, and `#F7F8F3` hover fill.
- **Emergency Stop (E-Stop)**: High-prominence `#DC2626` background, `#FFFFFF` bold text, with immediate tactile active states.

### Status Badges & Chips
- **Nominal / Connected**: `#DCFCE7` background, `#14532D` text, dot indicator pulsing at 1Hz.
- **Warning / Degraded**: `#FEF3C7` background, `#D97706` text.
- **Critical / Fault**: `#FEE2E2` background, `#DC2626` text.

### Telemetry Cards & Monitoring Viewports
- White surface (`#FFFFFF`) framed by `#E2E8F0`.
- Card headers utilize `Gmarket Sans` (weight 500, size 18px), while metric values render via `JetBrains Mono` (weight 700).

### Inputs & Selectors
- Standard text input with 1px `#E2E8F0` border, `Pretendard` 14px text, and `#16A34A` focus ring (2px offset).