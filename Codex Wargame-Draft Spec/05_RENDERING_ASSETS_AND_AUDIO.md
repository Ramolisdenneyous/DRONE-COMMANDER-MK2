# Missing Specification 5: Rendering, Battlefield Assets, And Audio

This document defines the visual and media production contract, including the battleground texture and terrain elements needed for the first playable map.

## 1. Rendering Architecture

React creates the battle screen and mounts one PixiJS host through a ref. PixiJS owns its application, scene graph, ticker, pointer hit testing, camera, and animation queue. The host destroys the Pixi application, textures it owns, listeners, and ticker callbacks on unmount.

React sends coarse commands such as `hydrateSnapshot`, `applyEventBatch`, `setSelection`, `setSettings`, and `resizeViewport`. PixiJS emits semantic events such as `hexSelected`, `unitSelected`, `cameraChanged`, and `animationBatchComplete`.

Do not push frame-by-frame positions through React state.

## 2. Logical-To-Visual Coordinates

The backend supplies pointy-top axial `(q, r)` coordinates. With logical hex radius `R`:

```text
x = R * sqrt(3) * (q + r / 2)
y = R * 1.5 * r
screen_y = y * ISO_Y_SCALE
```

Initial constants:

- `R = 48` logical pixels at design scale **TUNING**.
- `ISO_Y_SCALE = 0.72` **TUNING**.
- Camera rotation is fixed at zero.

The visual transform exists only in the frontend. Backend distances and lines remain axial.

## 3. Scene Layers

Create named containers in this stable order:

1. `ground_base`
2. `ground_decals`
3. `terrain_ground`
4. `terrain_structures`
5. `hex_overlays`
6. `units`
7. `effects_world`
8. `objectives_and_labels`
9. `battlefield_hud`

Units and tall terrain sort by projected base `screen_y`, then stable entity ID. Shadows stay with their owning entity but render below its body. World effects sort around units as specified by the animation cue; screen-space labels and controls stay above world effects.

The hex overlay should use a batched mesh or graphics layer rather than 2,500 independent interactive React elements.

## 4. Camera And Input

Required camera behavior:

- Pointer drag or middle-mouse drag pans.
- Wheel/pinch zooms around cursor/focal point.
- Keyboard pan and zoom controls have visible DOM equivalents.
- Zoom is clamped so a selected unit and nearby tactical context remain readable.
- A Home/center control frames the active unit; another frames the whole map.
- Starting camera frames both friendly deployment and the nearest objective, then moves to the commander when Round 1 begins.
- Camera motion cancels or shortens when reduced motion is enabled.
- Offscreen units and terrain are culled, but objective/active-unit edge indicators remain available.

Suggested zoom range is 0.35 to 1.75 **TUNING**. Camera state is presentation-only and may persist locally.

## 5. Battlefield Visual States

The active and selected actor must remain distinguishable. Required overlays:

- Reachable movement: green fill plus dotted boundary.
- Legal attack target: red bracket/reticle on the target, not only a red range ring.
- Weapon range boundary: thin red line.
- Commander signal: cyan/blue line with radio-wave ticks.
- Objective: amber marker with shape specific to objective type.
- Hazard: striped warning marker after detection.
- Invalid destination: blocked icon and short warning pulse.
- Path preview: directional chevrons and endpoint footprint.
- AOE preview: affected hex fill with explicit friendly-risk markers.
- Cover preview: shield icon and light/heavy label in the DOM inspector.

Use color, shape, icon, and motion redundantly. Overlays must remain legible over every ground variant.

## 6. Battleground Texture Specification

### 6.1 Base Ground Set

The VS requires one "damaged urban operations zone" base set:

- Four seamless 1024 by 1024 source textures, delivered as lossless PNG masters and web-optimized WebP runtime files.
- Neutral concrete/asphalt/rubble-ground family with restrained cool gray, charcoal, dusty mineral, and faded construction-mark colors.
- Medium-low contrast. Units, paths, and overlays must dominate.
- Even diffuse illumination with no baked directional shadows.
- No baked hex grid, buildings, barriers, craters, bodies, vehicles, readable text, logos, flags, or unique landmarks.
- No large repeated cracks or stains that make tiling obvious.
- Texture should tolerate rotation in 60-degree increments and mirroring, though runtime use should avoid obvious adjacent repetition.

Runtime chooses variants through map seed and blends transitions with decal masks. The hex grid is always a separate overlay.

### 6.2 Ground Decals

Provide transparent decals in 512 or 1024 pixel masters:

- small cracks
- dust and gravel scatter
- oil/dark stains
- faded lane markings without readable words
- small rubble scatter
- scorch marks
- drainage grates
- shallow mud/water patches

Decals contain no gameplay meaning unless the map data associates them with a terrain definition. Decorative decals must never imply cover or blockage.

### 6.3 Texture Acceptance

- A 3 by 3 repetition test has no dominant seam or unmistakable repeated landmark.
- Red, green, amber, cyan, and white overlays meet contrast/readability checks over every variant.
- Texture remains readable but unobtrusive at minimum and maximum supported zoom.
- Compression creates no visible block artifacts around grid lines or unit silhouettes.

## 7. Terrain Element Specification

Terrain uses transparent PNG masters and WebP runtime images with a separate logical footprint in map data. Tall art anchors at bottom center of its logical footprint and may extend upward, never sideways so far that it obscures unrelated selectable hexes.

### 7.1 VS Terrain Asset Set

At minimum:

- Low concrete barrier: three axis orientations, intact and damaged visual variants.
- Tall wall/building edge: three axis orientations and corner pieces.
- Building footprint/ruin: three small footprint stamps and one medium stamp.
- Rubble: six non-blocking variants.
- Crater: four variants.
- Wreckage: one small-drone, one medium-drone, and two large-platform variants.
- Road/lane overlays: three axis directions, bends, intersections, and end caps.
- Objective uplink: idle, friendly-controlled, contested, and opposition-controlled states.
- Smoke: animated effect atlas, not baked terrain.
- Mine: friendly/revealed marker plus hidden-state absence.

### 7.2 Orientation And Footprints

- Symmetric barriers need three axial orientations; asymmetric pieces need six directions.
- Every asset declares footprint hex offsets from an anchor.
- Collider/LOS metadata comes from terrain data, never alpha-pixel inspection.
- A visible base ring or hover outline reveals the logical footprint of tall art.
- Art variants share mechanics unless they use different terrain IDs.

### 7.3 Source Scale

Author runtime sprites at 2x design scale where practical. For `R = 48`, a one-hex ground footprint is approximately 83 by 96 design pixels before vertical compression; a 2x master should preserve at least 166 by 192 pixels for footprint detail. Tall structures may exceed that height.

Pack small related assets into atlases no larger than the platform-safe texture limit selected during implementation. Keep source masters separate from generated atlases.

## 8. Unit Asset Contract

Each unit asset set declares:

- base/selection footprint
- six facing directions or an explicitly directionless presentation
- idle/ready loop
- movement loop
- attack animation per weapon family
- hit reaction
- destruction or model-down animation
- optional ability animations
- frame timing, event markers, anchor, and bounds
- portrait/icon

Soldier squad models use numbered identities internally but need not display numbers constantly. Selection or inspection can reveal model numbers. Animations begin in a close stagger so a squad reads as coordinated rather than simultaneous clones.

The VS may begin with clearly labeled placeholder silhouettes, but placeholders must use the final manifest, anchors, footprints, and animation-state contracts. Do not couple game logic to temporary filenames.

## 9. Animation Contract

The backend emits semantic animation cues after commit. Example cue types:

- `move_path`
- `turn_to_face`
- `weapon_fire`
- `projectile`
- `impact`
- `damage_number`
- `status_apply`
- `model_destroyed`
- `unit_defeated`
- `objective_transition`
- `signal_pulse`
- `round_transition`

Each cue references domain event IDs and entity IDs. The client may combine or shorten cues but not change result order.

Suggested normal pacing **TUNING**:

- Movement: 100-140 ms per hex, capped near 1.2 seconds per movement action.
- Direct fire and impact: 300-700 ms total.
- Squad volley: 50-100 ms stagger, capped near 1 second.
- Status/ability: 250-800 ms.
- Round card shuffle: under 1 second and skippable.

Reduced motion replaces camera sweeps, shakes, card rotations, and long movement interpolation with short fades or immediate state updates. A "fast battle" setting shortens all nonessential pacing.

If an animation fails or the browser reconnects, clear incompatible queued cues and snap to the authoritative snapshot.

## 10. Initiative Cards

The commander card is always first. Non-commander cards follow backend initiative order. A card has stable dimensions and displays icon, unit name, side, initiative, Speed, HP/model count, statuses, and activation state.

Completed cards dim and rotate/tap only when motion is allowed; a check mark and text state remain the accessible cue. Defeated units leave the active row after their defeat animation but remain in battle history.

The optional shuffle/deal animation visualizes an already-decided order. It never delays backend readiness and is skippable.

## 11. Tactical Snapshot For Agents

Generate the agent snapshot server-side from semantic battle data, not by trusting a browser screenshot upload. Use simple icons and colors, a visible hex grid, active actor highlight, objectives, terrain blocks, and only information the agent is allowed to know.

Target a small image such as 768 by 512 or lower **TUNING**. The snapshot is optional and non-authoritative. Its renderer has golden-image tests for hidden-state filtering and entity placement.

## 12. Audio System

### 12.1 Categories

- UI press
- confirm/deploy
- invalid/disabled
- warning/danger
- tab switch
- initiative activation
- end turn/round
- weapon and impact families
- ability/status cues
- ambience
- music
- friendly TTS/radio

Each category has independent gain beneath master volume. Music, effects, UI, ambience, and voice have user controls. Mute state persists locally.

### 12.2 Playback Rules

- UI cues are under 250 ms where practical and rate-limited during repeated input.
- Invalid cues do not play for controls already visibly disabled unless an activation attempt occurs.
- Combat cues sync to animation markers, not backend commit timing.
- TTS is captioned by the same communications entry and never blocks activation.
- Only one TTS line plays at a time. New high-priority safety/objective speech may interrupt; routine lines queue with a bounded maximum.
- Muting voice stops playback immediately but keeps text.
- Browser autoplay restrictions are handled after the first user gesture without hiding controls.

### 12.3 TTS Queue

Queue entries contain communication ID, text hash, voice, priority, audio status, duration, and cancellation state. Drop or collapse stale routine lines when the battle has advanced too far; never play several rounds of delayed radio traffic.

## 13. Asset Manifest

Every runtime asset resolves through one versioned manifest entry:

```text
asset_id, category, source_master, runtime_url, content_hash,
width, height, anchor, atlas/frame data, variants, associated_definition_ids,
creator/provider, license_or_usage_status, approval_status, version
```

Runtime code requests asset IDs, not hand-built paths. Replacing an asset changes its content hash and manifest version. Browser URLs use hashed filenames or manifest versioning; manual cache-buster edits in React are not the primary mechanism.

Final assets require `approval_status = approved`. Generated drafts remain clearly marked and are excluded from production builds unless explicitly allowed.

## 14. Asset Production Workflow

1. Write a semantic asset brief with gameplay silhouette, footprint, viewpoint, lighting, palette, prohibited details, and required variants.
2. Generate or author source candidates.
3. Review at actual gameplay scale over the base texture and overlays.
4. Remove background, correct anchor and directional light, and build variants.
5. Export master and runtime formats.
6. Add manifest metadata and license/usage record.
7. Run atlas, missing-reference, dimensions, and alpha-bound tests.
8. Capture approved in-game screenshots before marking production-ready.

Image generation, ElevenLabs effects/voice, and Suno music may be used during production if Raymond chooses, but provider names do not become hard dependencies in the game client.

## 15. Performance Targets

On a representative desktop at 1920 by 1080:

- Target 60 FPS during idle/pan and at least 45 FPS during typical effects **TUNING**.
- Initial battle assets should become interactively ready within 5 seconds on local broadband after cache warmup **TUNING**.
- No frame-by-frame React rerender loop.
- No unbounded particle, texture, listener, ticker, or audio-node growth across tab switches/rematches.
- A 100-point battle with all units visible remains selectable and responsive.

Use texture atlases, culling, object pooling for repeated effects, and bounded animation queues. Measure before adding complexity.

## 16. Visual Verification

Automated browser checks capture at least:

- 1440 by 900 desktop battle
- 1280 by 720 minimum desktop
- 1024 by 768 tablet
- 390 by 844 phone stacked layout
- normal and reduced motion
- default and color-vision-safe overlay checks

Canvas pixel checks verify the battlefield is nonblank, textures are loaded, active/target overlays occupy expected regions, and no DOM panel covers the command controls. Manual review verifies visual hierarchy, tiling, depth sorting, labels, and hit areas.
