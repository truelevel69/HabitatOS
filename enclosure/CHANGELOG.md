# HabitatOS Changelog

---

## v0.07 · Thicket — Planned
> Status: Up next

---

## v0.06 · Basin — Released 2026-03-18
> Relay schedules, reminders system, and relay settings restructure.

### Added
- Relay schedules — new Schedules tab in Relay settings; each schedule has an enable toggle, channel selector (Ch 1–4), day-of-week pills (S M T W T F S), and one or more ON/OFF time windows; enforced automatically every sensor loop on the Pi
- Reminders — new 🔔 Reminders card on the settings landing; each reminder has a title, emoji icon, day pills, per-occurrence times with individual mark-done checkboxes, and an overdue mode toggle (Clear at midnight / Persist until checked)
- Reminder dashboard banners — blue banner per due reminder, turns amber when overdue >1h; snooze options: 5m, 10m, 15m, 30m, 1h, 2h, 6h, 8h, 12h, 24h; dismissing the banner does not mark the reminder done
- `/api/relay-schedules` GET + POST endpoints
- `/api/reminders` GET + POST endpoints
- `/api/reminders/<id>/done` POST endpoint — marks a specific occurrence done with timestamp

### Changed
- Relay settings restructured into two tabs: Labels & Icons / Schedules
- `relay_schedules` and `reminders` added to DEFAULT_CONFIG and persisted to config.json

---

## v0.05 · Fen — Released 2026-03-18
> Water quality panel overhaul, default day/night theme, layout preview, rotation fixes, alert improvements, canvas sharpness, and time/date system menu.

### Fixed
- Rotation submenu blank — duplicate IDs targeted hidden orphaned sp-rotation subpage; old subpage removed
- Alert dismiss re-triggered immediately — _alertDismissed flag added; clears until sensors recover
- Sparkline label blur — canvas scaled by devicePixelRatio for crisp rendering on high-DPI displays
- Display tab bodies not showing — dispSetTab now uniformly sets display:flex for all tabs
- Profile apply crash — ReferenceError on undeclared config variable stopped reload
- Freshwater fish profile — removed ambient DHT11 and water level; pure water chemistry only

### Added
- Water quality slide-out panel — 🧪 topbar button, auto-shows when WQ sensors configured
- Default theme with day/night variants — default-day (warm light) / default-night (dark slate)
- Day/night inline controls in Theme tab — auto-cycle toggle and force ☀️/🌙 buttons
- Layout preview panel in Display → Layout — 200px live preview of all 5 layout modes
- Per-rule enable/disable toggle in Rotation → Schedule
- History page fully working — range filter, chart, table with status pills, CSV export
- Time & Date tab in System settings — live clock, hour/min/day/month/year +/- controls, 12h/24h toggle, timezone (30+ zones incl. Zulu), Set button

### Changed
- Rotation auto-rotate off now automatically disables fade
- Settings scroll — min-height:0, touch-action:pan-y, -webkit-overflow-scrolling:touch applied globally

---

## v0.04 · Burrow — Released 2026-03-17
> Dashboard layout overhaul, day/night cycle, idle improvements, profile fix.

### Fixed
- Profile switching ReferenceError fixed
- Sensor grid activeReadings() mismatch fixed
- Idle screen wake flash removed
- Memory shown in GB
- Dual-line sparkline removed
- History page route added
- WQ button shows on page load

### Added
- Day/night cycle engine with auto-schedule
- Manual toggle button in topbar
- Idle screen sensor selector
- Water quality slide-out panel
- History page with chart and CSV export

### Changed
- WQ card replaced by slide-out panel
- Idle & Dim expanded with day/night controls

---

## v0.03 · Canopy — Released 2026-03-17
> Dashboard layout overhaul, settings restructure, boot screen polish, console rebuild.

### Fixed
- 4x2 full-screen grid
- Boot starts automatically on Pi
- Console enter key rebuilt
- Sounds unified

### Added
- 4x2 grid with pagination
- Console with 30+ commands
- Theme rotation in Display tab
- 3 new sounds

### Changed
- Settings: 7 cards → 5
- Display: 4 tabs → 5
- Profile: single → 2 tabs

---

## v0.02 · Sprout — Released 2026-03-17
> Bug fixes, relay panel, branding system, boot screen overhaul.

### Fixed
- Sensor config overflow fixed
- ctbTheme duplicate declaration crash fixed

### Added
- Relay slide-out panel
- Full boot sequence
- /api/version, CHANGELOG

### Changed
- Display split into 4 sub-tabs
- Versioning formalised

---

## v0.01 · Tadpole — Released 2026-03-17
> First complete build.

### Added
- Flask + SQLite backend, 15 sensor drivers, 7 profiles
- 5 layout modes, 6 sparkline styles
- 15 themes + custom builder, theme rotation
- 12 sounds, idle screen, CSV export, alert banner

---

## Version Roadmap

| Version | Codename  | Status    |
|---------|-----------|-----------|
| v0.01   | Tadpole   | Released  |
| v0.02   | Sprout    | Released  |
| v0.03   | Canopy    | Released  |
| v0.04   | Burrow    | Released  |
| v0.05   | Fen       | Released  |
| v0.06   | Basin     | Released  |
| v0.07   | Thicket   | Planned   |
| v1.07   | Amphibian  | Milestone |

---

## Versioning Scheme

**0.x series** — development versions, named after habitat features (Tadpole → Thicket).
Each minor bump (0.01, 0.02 …) represents a completed named checklist.

**1.x.y series** — begins at v1.07 · Amphibian, carrying the minor number forward from Thicket.
All three numbers are independent counters — none ever resets.

| Number | Range | Format | Role | Behaviour |
|--------|-------|--------|------|-----------|
| Major | 1–99 | `1`, `2` … `99` | Generation | Version change |
| Minor | .01–.99 | `.07`, `.08` … `.99` | Feature set | Feature additions, removals, and major bug fixes |
| Patch | .0–.9 | `.0`, `.1` … `.9` | Fix | Minor bug fixes and system patches |

**Major bump to v2.x** — reserved for full architecture rewrites only.
