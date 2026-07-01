# Phase 5: Best Run Replay Mode - MVP Spec

Status: **Deferred** (waiting for Phase 3 Fast Capture + Phase 4 Auto-Calibration to stabilize first)
Target Version: `v1.3.0`
Estimated Effort: 14-21 hours (~2-3 dev days)

---

## 1. Goal

Let user play 1 best run themselves, bot records action timeline, then bot replays that timeline in future rounds. Reduces detector workload on maps where the obstacle pattern is fixed.

**Not replacing** Hybrid Detection - it becomes a fallback when replay sync fails.

---

## 2. MVP Scope

Ship exactly these 5 things:

1. **Record Mode** - GUI button captures user's actions during a live round
2. **Basic Replay** - Read JSON profile, execute actions at their timestamps
3. **Slide Duration Support** - Records and replays press-and-hold slides correctly
4. **Start-State Check** - Single anchor image at t=0 to verify round starts from same state
5. **Detector Fallback** - If start-state doesn't match, fall back to existing Hybrid Detection

---

## 3. Out of Scope (Deferred to v1.4+)

Explicitly NOT in MVP:

- Map fingerprinting (auto-detect which map is being played)
- Profile scoring / success-rate tracking / auto-disable bad profiles
- Kalman filter for drift smoothing
- Multiple profiles per map (ensemble replay)
- Anchor sync every 5 seconds (only start-state anchor in MVP)
- Character / pet / treasure context recording
- Profile marketplace / sharing / cloud sync
- ML classifier integration
- Auto-template learning from crash logs
- BONUSTIME / Kingdom Race / Trophy Race special handling

Rationale: Ship a working single-map replay first. Field-test reveals what enhancement is worth building next.

---

## 4. Replay Profile Data Structure

```json
{
  "profile_name": "best_run",
  "resolution": "1280x720",
  "created_at": "2026-07-01T18:00:00",
  "recorded_duration_sec": 45.32,
  "start_anchor": "start.png",
  "actions": [
    { "t": 1.25, "action": "jump" },
    { "t": 1.48, "action": "double_jump" },
    { "t": 3.10, "action": "slide", "duration": 0.35 },
    { "t": 5.60, "action": "jump" }
  ]
}
```

Field notes:
- `t` = seconds since round start (round start = when `state_run` enters main loop after `wait_ingame` returns true)
- `action` = one of `jump`, `double_jump`, `slide`
- `duration` = **required for slide** (press-and-hold duration in seconds), omitted for taps
- `resolution` = LDPlayer resolution the profile was recorded at - warn if replay resolution differs
- `start_anchor` = filename of PNG image saved next to the JSON

---

## 5. File Location

Windows: `%LOCALAPPDATA%\CookieGame\replay_profiles\`
Mac:     `~/Library/Application Support/CookieGame/replay_profiles/`

Per-profile files:
```
replay_profiles/
├── best_run.json
├── best_run_start.png       (start anchor, ~500KB PNG or ~50KB JPEG)
└── (future) best_run_stats.json
```

Naming: user-provided profile_name, kebab-case. Duplicates auto-append `_2`, `_3`, etc.

---

## 6. Record Flow

**Trigger**: User clicks `Record` button in Tkinter GUI

```
User clicks Record
    v
GUI shows dialog: "Bot will stop controlling. Play 1 round yourself.
                   Recording starts when you enter game state (BONUSTIME complete)."
    v
Bot enters RECORD_MODE
    v
Bot still runs state machine (REROLL, RUN, RESULT) but:
  - No adb_tap calls
  - No adb_slide calls
  - state_run captures user's touch events via ADB
    v
Round starts (state_run main loop begins)
    v
Record loop:
  - Save first frame -> start_anchor.png
  - Poll `adb shell getevent` OR `adb shell dumpsys input` for touch events
  - Convert touch to action: tap at (80, 670) -> jump, hold at (1200, 670) -> slide with duration
  - Append to actions list: {"t": elapsed_since_round_start, "action": "..."}
    v
Round ends (Result screen detected)
    v
GUI dialog: "Save profile? Name: [best_run__]  [Save] [Cancel]"
    v
Save to replay_profiles/{name}.json + {name}_start.png
    v
Return to normal bot control (or stay stopped, user's choice)
```

Touch event detection strategy:
- **Preferred**: parse `adb shell getevent -lt /dev/input/event*` for tap/hold events
- **Fallback**: OpenCV frame diff to detect when Cookie animation changes (jump/slide poses have distinct silhouettes)

Slide detection: if touch event stays on Slide button for > 100ms, record as `{"action": "slide", "duration": <hold_time>}`. Otherwise record as instant tap (jump/double_jump).

Double jump: two `jump` actions within 250ms merged into single `{"action": "double_jump"}` entry.

---

## 7. Replay Flow

**Trigger**: User selects profile from GUI dropdown and clicks `Replay`

```
User selects profile -> clicks Replay
    v
Bot loads profile.json + start_anchor.png
    v
Bot enters normal state machine (REROLL, RUN, RESULT)
    v
When state_run begins:
    -> Read first frame
    -> Compare with start_anchor (SSIM > 0.8) -- see Section 8
        |
        +-- Match -> REPLAY_MODE active
        +-- No match -> fall back to Hybrid Detection (Section 9)
    v
REPLAY_MODE main loop:
    - t_start = time.time() when replay mode enters
    - Iterate through profile.actions in order
    - When elapsed >= action.t:
        * action == "jump"        -> adb_tap(BTN_JUMP)
        * action == "double_jump" -> adb_tap(BTN_JUMP); sleep(120ms); adb_tap(BTN_JUMP)
        * action == "slide"       -> adb_hold(BTN_SLIDE, duration)
        * Increment action index
    - Continue until:
        * All actions consumed (rest of round -> Hybrid Detection fallback)
        * Result screen detected (round ended)
        * Freeze detected (bot died, replay failed)
    v
Round ends -> log replay result (success / freeze / drift)
```

Timing precision: `time.perf_counter()` used for t_start and elapsed, not `time.time()`. Sub-millisecond accuracy.

Cadence: replay loop checks `time.perf_counter() - t_start >= next_action.t` every 20ms (independent of screen capture rate).

---

## 8. Start-State Check

Single anchor comparison at round start. Not per-5s in MVP.

```python
def start_state_matches(current_frame, anchor_path, ssim_threshold=0.80):
    anchor = cv2.imread(anchor_path)
    if anchor is None:
        return False
    if current_frame.shape != anchor.shape:
        return False   # resolution mismatch
    gray_curr = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    gray_anch = cv2.cvtColor(anchor, cv2.COLOR_BGR2GRAY)
    score = ssim(gray_curr, gray_anch)   # skimage.metrics.structural_similarity
    return score >= ssim_threshold
```

If SSIM library unavailable, fall back to normalized cross-correlation via `cv2.matchTemplate` on downscaled frames.

Threshold rationale:
- 0.80 = same map, same character, similar biome start state
- Higher (0.9+) = too strict, minor visual variance breaks it
- Lower (0.7-) = false matches (different maps considered "same")

---

## 9. Detector Fallback

Replay Mode is **not** all-or-nothing. Detector Fallback triggers on:

1. **Start-state mismatch** at round begin -> use Hybrid Detection for whole round
2. **Freeze detected during replay** (frame hasn't changed for 3s) -> abort replay, switch to Hybrid Detection mid-round
3. **All actions consumed** but round still running -> Hybrid Detection takes over for remaining time
4. **User manually cancels** replay via GUI -> switch to Hybrid Detection

State flag:
```python
_REPLAY_STATE = "IDLE" | "REPLAYING" | "FALLBACK_HYBRID"
```

Transition logging:
```
[replay] start-state match SSIM=0.87 -> REPLAYING
[replay] action jump at t=1.25s
[replay] action double_jump at t=1.48s
...
[replay] all actions consumed at t=45.32s -> FALLBACK_HYBRID
```

---

## 10. GUI Changes

Add 2 buttons + 1 dropdown to Tkinter main window:

Current layout:
```
[Start Bot]  [Stop Bot]  [Emergency Stop]
```

New layout:
```
[Start Bot]  [Stop Bot]  [Emergency Stop]
[Record]  [Replay: dropdown-of-profiles v]
```

`Record` button behavior:
- Click -> confirmation dialog -> if OK, enter RECORD_MODE
- While recording -> button text changes to `Stop Recording`
- Click again -> stop, prompt for profile name, save

`Replay` dropdown:
- Populated from `%LOCALAPPDATA%\CookieGame\replay_profiles\*.json`
- Empty state: "(No profiles - Record one first)"
- Selecting one -> next Start Bot uses that profile

Config toggle in `config.yaml`:
```yaml
replay:
  enabled: false                       # default off, user must opt in
  active_profile: null                 # profile filename without .json
  start_state_ssim_threshold: 0.80
  double_jump_gap_ms: 120
  fallback_on_freeze: true
```

---

## 11. Implementation Tasks

Ordered checklist for MVP:

- [ ] **T1** - Add `replay:` section to `config.yaml` with defaults
- [ ] **T2** - Create `src/replay.py` module with:
  - [ ] `ReplayRecorder` class (captures touch events during round)
  - [ ] `ReplayPlayer` class (loads profile, executes at timestamps)
  - [ ] `save_profile(name, actions, start_frame)` helper
  - [ ] `load_profile(name)` helper
  - [ ] `list_profiles()` for GUI dropdown
- [ ] **T3** - Add `_start_state_matches(frame, anchor)` helper (SSIM comparison)
- [ ] **T4** - Modify `state_run()` to check `_REPLAY_STATE`:
  - If IDLE -> existing Hybrid Detection logic
  - If REPLAYING -> `ReplayPlayer.step()` at each iteration, fallback if freeze/timeout
- [ ] **T5** - Modify `cookiegame.py` (Tkinter GUI):
  - [ ] Add `Record` button + click handler
  - [ ] Add `Replay` dropdown populated from profiles dir
  - [ ] Add save-profile dialog after recording ends
- [ ] **T6** - Touch event capture via `adb shell getevent -lt`:
  - [ ] Parse output stream in background thread
  - [ ] Filter events by input device (LDPlayer touch input)
  - [ ] Convert coordinates to action label based on button positions
- [ ] **T7** - Slide duration handling:
  - [ ] Detect press vs release events -> compute hold duration
  - [ ] If hold > 100ms and position matches BTN_SLIDE -> record as slide with duration
- [ ] **T8** - Detector Fallback integration:
  - [ ] Reuse existing freeze detection code path
  - [ ] Add `_REPLAY_STATE = "FALLBACK_HYBRID"` transition
  - [ ] Log fallback trigger reason
- [ ] **T9** - Testing:
  - [ ] Manual test: record 1 round, immediately replay same round
  - [ ] Test resolution mismatch handling (record 1280x720, try replay 1920x1080)
  - [ ] Test freeze mid-replay -> fallback triggers
  - [ ] Test empty actions list (short recording, replay does nothing gracefully)
- [ ] **T10** - Documentation:
  - [ ] Update `README.md` with Record/Replay usage
  - [ ] Screenshot of GUI additions

---

## 12. Future Enhancements (post-MVP)

Order of priority for v1.4+:

1. **Multi-anchor sync** - anchor image at t=5s, 10s, 15s to correct mid-round drift
2. **Map fingerprint** - auto-select which profile to replay based on first-frame hash
3. **Profile scoring** - track success rate per profile, auto-disable if < 60%
4. **Character context** - detect Cookie identity from lobby screen, apply per-character profiles
5. **Boost/treasure context** - detect active boosts, apply per-boost profile variants
6. **Time-offset correction** - Kalman-smoothed drift adjustment between anchors
7. **Ensemble replay** - try 2-3 profiles per map, pick highest-success one
8. **Profile export/import** - user can share profiles via file
9. **Cloud sync** - shared community profile repository
10. **ML fallback** - CNN classifier when Hybrid Detection uncertain

---

## Open Questions for MVP Implementation

- **Touch event capture reliability**: Does `adb shell getevent -lt` work on all LDPlayer versions? Fallback plan if not?
- **Round-start detection**: How exact is "state_run begins" in terms of frame count? Might need offset compensation.
- **BONUSTIME handling**: BONUSTIME has different mechanics - skip recording it, only record actual round?
- **Concurrent input**: What if user taps Jump and Slide simultaneously mid-record? Probably an edge case, but define behavior.
- **Profile schema versioning**: Add `"schema_version": 1` field for future migration compatibility?

Address these during Phase 5 implementation kickoff, not now.
