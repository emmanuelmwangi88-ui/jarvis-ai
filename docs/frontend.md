# Frontend — Sakura AI

A no-build web app served from `ui/static/`, split into focused modules:

```
static/
  index.html          markup only (structure, blossom-tree SVGs, palette + settings modals)
  css/base.css        layout + components, 100% CSS-variable driven
  js/themes.js        theme palettes + settings/theme modal + persistence
  js/background.js    falling-petal canvas engine (theme-aware)
  js/app.js           chat streaming, tools, voice, controls, command palette
```

Hand-written CSS, inline SVG icons + **cherry-blossom trees**, a CSS aurora background,
an animated **petal canvas**, and a live AI "reactor orb". Google Fonts (Outfit / Inter /
JetBrains Mono) enhance a real browser and fall back to system fonts offline. Because the
CSS/JS load from `/static/...`, the full experience needs the app served by `ui_server.py`
(opening the HTML from disk alone won't pull the assets).

## Themes & settings
The gear icon (rail + header) opens a **Settings** modal with a theme picker and
background controls. Six built-in themes — **Sakura, Midnight Aurora, Sunset, Forest,
Ocean, Monochrome** — each defined in `themes.js` as a set of CSS variables plus a petal
palette. Selecting one rewrites the variables on `<html>` live and saves to
`localStorage`. Toggles for falling petals, blossom trees, and the aurora glow, plus a
petal-density slider, are persisted too. Add a theme by dropping another entry in the
`THEMES` object — no other file changes needed.

## Concept
A **conversation-centric, agent-forward** interface (deliberately different from a
dashboard). A soft **sakura** palette — rose / pink / warm-gold on deep plum glass —
with cherry-blossom petals drifting down the background (`<canvas id="petals">`, a
lightweight `requestAnimationFrame` engine, ~40–46 petals scaled to viewport). The
right rail is an **AI Core**: a living blossom-tinted orb that changes color and speed
with the agent's state, plus autonomy controls, telemetry, an activity stream, and the
self-learning panel.

## Layout
```
┌ rail ┬ center ─────────────────────────────┬ AI Core ──────────────┐
│ logo │ header: Sakura AI · conn · reflect │  ◉ reactor orb        │
│ Chat │                                      │  state / profile      │
│ Code │  streaming conversation feed         │  Autonomy segmented   │
│ Rsrch│  (tokens appear as generated)        │  Locked/Trusted/Unl.  │
│ Term │  tool chips · authorization cards    │  capability chips     │
│ Voice│                                      │  live telemetry       │
│  ⌘K  │                                      │  activity stream      │
│  +   │  ┌ floating composer: screen·mic·send│  self-learning skills │
└──────┴──────────────────────────────────────┴───────────────────────┘
```

## The reactor orb (AI state)
`orb(state)` swaps a CSS class: **idle** (slow rose breathing), **thinking** (fast spin),
**acting** (gold, running a tool), **speaking** (bright glow), **listening** (pink, mic
open). It's the at-a-glance signal of what the agent is doing.

## Streaming
`send()` POSTs to `/api/chat/stream` and reads the `ReadableStream`, parsing SSE frames:
- `route` → sets the orb to *thinking* and records role/model.
- `token` → appends to the current bubble with a blinking caret (live typing).
- `tool` → orb to *acting*, adds a tool chip + an Activity Stream entry.
- `confirm` → renders an **Authorize / Deny** card; the choice re-sends with `confirm`.
- `done` → finalizes Markdown, orb to *speaking* then *idle*; refreshes telemetry.

This is what makes replies feel instant even on a small local model.

## Everything is wired
| UI element | Endpoint |
|---|---|
| Streaming chat | `POST /api/chat/stream` |
| Autonomy segmented control | `POST /api/autonomy` (Locked/Trusted/Unleashed) |
| Capability chips (Shell/Files/Web/Audio) | `GET/POST /api/settings` — live tool gates |
| Live telemetry (t/s, CPU, mem) | `GET /api/metrics` |
| Self-learning panel + skill count | `GET /api/learning` |
| Activity stream | tool events from the chat stream + policy changes |
| Reflect & learn (⚡) | `POST /api/reflect` |
| Voice (hold mic) | `POST /api/voice` |
| New chat / ⌘N | `POST /api/reset` |
| Command palette / ⌘K | client-side, calls the above |
| Connection + model chip | `GET /api/status` |

## Command palette (⌘K)
A filterable overlay with New chat, Reflect, Analyze screen, the three autonomy profiles,
Benchmark, Flush cache, and Export log. Arrow keys + Enter.

## Restyling
All colors are CSS variables in `:root` (`--teal`/`--emerald`/`--gold` now hold the
sakura rose/pink/gold values, plus the surface ramp). Change them to reskin. The petal
colors live in the `COLORS` array inside the petal engine, and petal density scales with
`W*H`. Fully self-contained, so it also renders in a no-network preview (values show
`—`, daemon reads offline).
