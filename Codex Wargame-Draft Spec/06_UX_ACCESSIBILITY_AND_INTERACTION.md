# Missing Specification 6: UX, Accessibility, And Interaction

This document defines how the rules become a usable command experience. The battlefield remains the primary surface; interface chrome exists to help the player understand and act.

## 1. Experience Principles

- Show the active actor, remaining actions, current objective, and accepted input at all times.
- Present legal choices before asking the player to reason about hidden rules.
- Keep battle tempo brisk without hiding mechanical results.
- Use consistent military-console styling without sacrificing reading comfort.
- Make every canvas interaction available through an equivalent DOM control.
- Never rely on color, sound, animation, or TTS alone.

## 2. Navigation Model

Primary destinations are Mission Prep, Battle, and Debrief. Their availability follows session state:

- `DRAFT`: Mission Prep enabled; Battle and Debrief unavailable.
- `ACTIVE`: Battle enabled and selected; prep is read-only summary.
- Terminal: Debrief selected; Battle remains reviewable but read-only.

Settings and help are utility dialogs, not primary tabs. Reset/abort are placed in an overflow menu with confirmation.

## 3. First-Run Onboarding

The first visit opens a brief intro over or immediately before Mission Prep. It includes the game name, literal premise, a short tutorial video or placeholder, captions/transcript, Skip, and Continue.

The tutorial explains only:

- the commander is the player's vulnerable battlefield unit
- squads and drones act from intent-level orders
- movement, attack, signal, objective, and initiative overlays
- the backend resolves results

Skipping is immediate and remembered locally. Help can replay the tutorial. The intro must not become a marketing landing page that delays access to the game.

## 4. Mission Prep

Mission Prep is one coherent workflow with a visible stepper and persistent army summary:

1. Commander avatar.
2. Commander loadout.
3. Three RAM abilities.
4. Mode and point cap/mission.
5. Army construction.
6. Review and deploy.

### 4.1 Commander Selection

Avatar choices show portrait, name/voice preview if available, and no mechanical stat difference. Loadouts show final stats, weapon, passive, and RAM affinity. Ability selection uses checkboxes with a `3 of 3` counter; choices beyond three are disabled until one is removed.

### 4.2 Army Builder

The builder uses a filterable unit list and a selected-force roster. Unit entries have stable compact dimensions and show role, cost, models, Speed, Attack, Damage, Defense, Armor, HP, abilities, and preview. Details expand in a side inspector rather than nested cards.

Always show:

- points spent and cap
- points remaining
- unit count and limit
- required choices
- validation messages

Add/remove controls use familiar plus/minus or quantity steppers with tooltips and accessible names. Invalid additions explain the exact cap or limit. Deploy remains disabled until advisory validation succeeds.

If the player leaves points unspent, Review states that the opposition is built to the selected cap and asks for confirmation once; it does not prevent deploy.

### 4.3 Deploy States

On Deploy:

- Disable repeated submission and show progress steps: validating, building opposition, preparing map, deploying units.
- A retry uses the same idempotency key.
- On recoverable failure, keep every prep choice and offer Retry.
- On success, transition to Battle only after the authoritative battle snapshot exists.

## 5. Battle Console Layout

### 5.1 Wide Desktop, 1200 Pixels And Above

- Top bar: mission, round, objective, connection/audio/settings controls.
- Initiative strip: full activation order beneath top bar.
- Main region: battlefield takes available width and height.
- Left inspector: selected unit and terrain, collapsible.
- Right communications rail: current directive, radio/system history, command composer, collapsible.
- Commander action tray: anchored along the battlefield bottom, never covering the selected unit when the camera can compensate.

The side panels are page regions, not floating decorative cards. The battlefield remains visibly larger than either rail.

### 5.2 Tablet And Narrow Desktop, 768-1199 Pixels

The battlefield fills the upper region. Inspector and communications become tabs in a stable lower drawer. Initiative scrolls horizontally with the active card automatically visible. The commander action tray stays above the drawer.

### 5.3 Phone, Below 768 Pixels

Use a stacked battle layout:

- compact status bar
- horizontally scrollable initiative strip
- fixed-aspect battlefield viewport with pan/zoom
- segmented lower tabs for Actions, Unit, Objective, and Radio

Full battle remains possible, but desktop is the primary target. Touch controls are at least 44 by 44 CSS pixels and no essential action depends on hover.

## 6. Active Unit And Turn Awareness

When activation changes:

- Camera offers a brief frame/center motion unless the user is manually inspecting elsewhere.
- Active unit receives a persistent outline and ground marker.
- Initiative card becomes selected with text/icon state.
- DOM heading announces actor and side.
- Remaining actions are shown as Standard, Move, and Minor tokens with spent/downgraded state.

While an agent-controlled unit acts, the player may pan, inspect, read history, change playback speed, or mute. Mechanical controls remain disabled with the reason "Unit autonomy resolving."

The player may pause before the next activation for inspection, but pausing does not cancel an in-flight provider request unless explicitly configured.

## 7. Commander Interaction

### 7.1 Movement

1. Select Move.
2. Battlefield shows reachable cells and path on hover/focus.
3. Select a destination.
4. Inspector shows cost, cover, and exposure tags.
5. Confirm immediately for ordinary movement; require a second confirmation only for known hazard or severe irreversible risk.
6. Backend resolves and animations play.

Keyboard users navigate offered destinations as a list grouped by tactical label instead of traversing 2,500 cells.

### 7.2 Attack

1. Select weapon/Attack.
2. Legal targets receive reticles; target list is available in DOM.
3. Select target to see range, LOS, cover, hit formula, and predicted AOE.
4. Confirm when friendly fire is possible; otherwise execute.
5. Show rolled dice and result in a concise expandable combat entry.

Do not display a fabricated percentage unless it is calculated exactly from the 3d6 distribution and effective modifiers.

### 7.3 RAM Abilities

Ability controls show icon, name, RAM cost, action cost, target rules, and current availability. Disabled controls state the reason: insufficient RAM, wrong action, no painted target, already used, or no legal target.

The signal overlay is toggleable and appears automatically when selecting a signal-dependent ability.

### 7.4 Ending Activation

End Activation is a clear command with an icon and text. If meaningful actions remain, one nonmodal warning summarizes them and allows End Anyway. The player can choose "Do not warn again this battle."

## 8. Directives And Communications

During commander activation, the composer edits a global directive or a selected unit directive. Scope is a segmented control, with selected unit shown explicitly. Suggested tactical commands are buttons only when they are genuine commands such as Hold, Advance, Protect Commander, or Prioritize Objective.

Submitting a directive gives immediate visual/audio acknowledgement and adds the exact text to communications. Directives lock when commander activation ends.

Communications entries have types and visual markers:

- player directive
- friendly radio
- system combat result
- objective update
- warning/error
- provider/fallback notice

History follows the newest entry only when the player is already near the bottom. If they have scrolled up, show a "New traffic" control without moving their reading position.

Dice detail, event IDs, and debugging data are collapsed by default. Radio text and mechanical result are visually distinct so a flavorful sentence cannot be mistaken for the rules result.

## 9. Terrain And Unit Inspector

Selecting a unit shows public stats, models/HP, weapon ranges, ammunition, abilities, statuses, signal state, activation state, and current directive. Selecting terrain shows movement cost, cover, LOS, hazard, and destructibility.

Long descriptions are concise and plain-language first. Exact formulas are available in a secondary Rules detail. Avoid unexplained abbreviations; RAM, AOE, LOS, HP, and TTS receive tooltips or glossary access.

## 10. Initiative Strip

Cards have fixed width/height so HP, statuses, long names, and active animations cannot reflow the strip. Use truncation only with an accessible full name and tooltip.

States are:

- waiting
- active
- completed
- defeated
- skipped/carried
- resolving/fallback

The commander card is visibly pinned first. Completed state uses icon and text as well as dimming. New-round deal animation is optional, under one second, skipped under reduced motion, and never hides the final order.

## 11. Debrief

Debrief begins with literal Victory, Defeat, Draw, or Aborted status and objective outcome. It may show:

- rounds and elapsed play time
- commander survival and RAM use
- friendly models/units lost
- opposition units defeated
- objective timeline
- key combat events
- provider fallback count, shown only in diagnostic detail
- campaign unlock/progression when applicable

Actions are Rematch, Return to Mission Prep, Review Battlefield, and Submit Feedback. Rematch states whether it reuses armies/map seed or creates a new seed.

Feedback is never required. It states what session context will be attached and provides a way to omit transcript/communications.

## 12. Visual System

Use a dark neutral foundation rather than a single-hue dark blue interface. Suggested semantic families:

- near-black/charcoal surfaces
- off-white primary text
- green for legal/confirmed
- amber/yellow for objective/caution
- red for hostile/danger
- cyan for signal/information
- neutral gray for spent/disabled

Glows are restrained and never reduce text contrast. Tactical grids, scanlines, and HUD effects are subtle, static under reduced motion, and absent behind dense text.

Cards and panels use 8-pixel radius or less. Do not put cards inside cards or turn every section into a floating container. Use familiar icons from the existing icon library, preferably Lucide when available, with visible labels for primary commands and tooltips for unfamiliar icons.

Typography uses a readable sans-serif, normal letter spacing, mixed case for prose, and stable sizes by component rather than viewport-width scaling. Avoid long all-caps text and overly condensed tactical fonts for body copy.

## 13. Interaction Feedback

Every interactive control has:

- default
- hover where supported
- pressed/active
- disabled with reason
- focus-visible
- loading/pending when asynchronous

Accepted actions visibly change state within 100 ms through pending feedback even when the server result takes longer. Short UI sounds are optional and respect mute. Invalid actions show a nearby explanation and do not rely on a warning chirp.

Buttons keep stable dimensions while loading. Replace labels only when space remains stable; otherwise use an adjacent progress indicator and preserve the command name for assistive technology.

## 14. Accessibility Requirements

Target WCAG 2.2 AA for DOM surfaces and equivalent access to canvas information.

Required:

- Complete keyboard operation for prep, commander actions, directives, settings, and debrief.
- Visible focus with logical order and no focus traps outside modals.
- Screen-reader names, roles, values, disabled reasons, and state changes.
- DOM unit list, target list, destination options, objective state, and terrain details equivalent to canvas selection.
- Polite live announcements for activation and routine results; assertive only for terminal or serious connection state.
- Captions/transcripts for tutorial, TTS, and meaningful audio.
- Reduced motion and fast-animation settings.
- No color-only meaning and color-vision-safe overlay combinations.
- Text contrast at least 4.5:1 for normal text and 3:1 for large text/UI boundaries where applicable.
- Touch targets at least 44 by 44 CSS pixels.
- Zoom to 200% without loss of command access or text overlap.
- Readable line length and spacing in communication history, with an optional text-size setting.

Canvas itself may be `aria-hidden` when complete semantic DOM controls are provided; do not expose thousands of raw graphics nodes as a noisy accessibility tree.

## 15. Connection And Failure States

### Initial Loading

Show one stable shell with specific status: loading catalog, restoring session, or loading battlefield assets. Do not flash an empty battlefield.

### Reconnecting

Display a nonblocking connection banner. Disable mutation, retain camera/inspection, reconnect using last event ID, then reconcile snapshot before re-enabling commands.

### Provider Fallback

Use a quiet communications entry that autonomy fallback is active. Do not interrupt with a modal.

### Content Version Mismatch

Prevent mutation, explain that the game content changed, and offer safe reload. Never let an old client submit guessed IDs.

### Fatal Recoverable Error

Preserve session and show Retry, Export Diagnostic ID, and Abort/Return options as appropriate. Do not expose stack traces.

## 16. UX Acceptance

- A new player can deploy a legal 15-point army without external instructions.
- The active actor and objective are identifiable in every responsive layout.
- Every commander action available on canvas is also available by keyboard/DOM list.
- A player can distinguish radio flavor from mechanical result.
- A player who scrolls up does not lose reading position when events arrive.
- Text, cards, counters, and buttons do not overlap at required viewports or 200% zoom.
- Muted, reduced-motion, keyboard-only, and screen-reader paths can complete a battle.
- Refresh/reconnect never creates duplicate input or leaves controls enabled against stale state.
