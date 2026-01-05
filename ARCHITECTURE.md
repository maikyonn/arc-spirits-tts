# Arc Spirits TTS - Architecture

## File Structure

```
src/
├── Global.ttslua                    # Entry point, TTS lifecycle, XML callbacks
│
├── state/
│   └── GameState.ttslua             # Central state store, serialization
│
├── api/
│   ├── SupabaseLib.ttslua           # Supabase API data loading
│   ├── WebRequestLib.ttslua         # HTTP GET/POST utilities
│   ├── AssetLoaderLib.ttslua        # Asset preloading, bag spawning
│   └── GameSyncLib.ttslua           # Sync game state to backend
│
├── game/
│   ├── PlayerMatLib.ttslua          # Player mat tracking, spirit slots
│   ├── NavigationLib.ttslua         # Realm navigation selection
│   ├── MarketLib.ttslua             # Spirit market, refill, purge
│   ├── TraitLib.ttslua              # Trait counting from spirits
│   ├── DiceLib.ttslua               # Dice breakpoint data access
│   └── CharacterSelectLib.ttslua    # Character selection, game start
│
├── util/
│   ├── SearchLib.ttslua             # Physics-based object searching
│   ├── SpawnLib.ttslua              # Object spawning utilities
│   ├── TableLib.ttslua              # Table manipulation
│   ├── UtilLib.ttslua               # General utilities
│   ├── ObjectTemplateLib.ttslua     # TTS object data templates
│   └── TtsLuaAdditions.ttslua       # Vector/Color extensions
│
└── ui/
    ├── UILib.ttslua                 # UI orchestrator, XML generation
    ├── UITheme.ttslua               # Colors, sizes, positions
    ├── UIComponents.ttslua          # Reusable component builders
    ├── GlobalUI.ttslua              # Navigator, announcements
    ├── SidebarUI.ttslua             # Player sidebar
    ├── LobbyUI.ttslua               # Character select screen
    ├── DebugPanelUI.ttslua          # Debug information
    ├── DiceSpawnerUI.ttslua         # Dice spawner panel
    ├── RuneSelectorUI.ttslua        # Rune selection
    └── ResourceTrackerUI.ttslua     # Blood/VP tracker
```

---

## GameState Table

All persistent game state lives in `state/GameState.ttslua`.

### Core Session State

| Field | Type | Persisted | Description |
|-------|------|-----------|-------------|
| `fresh` | boolean | Yes | `true` if mod never loaded before |
| `gameStarted` | boolean | Yes | `true` after "Start Game" clicked |
| `gameId` | string | Yes | Unique session ID (`game_YYYYMMDD_HHMMSS_XXXX`) |
| `navigationCount` | number | Yes | Completed navigation rounds |

### Character Selection

| Field | Type | Persisted | Description |
|-------|------|-----------|-------------|
| `selectedCharacters` | table | Yes | `playerColor -> characterName` |
| `availableCharacters` | array | Yes | List of playable character names |
| `characterMatData` | table | Yes | `charName -> { imageUrl, chibiUrl, ... }` |

### Per-Player State

| Field | Type | Persisted | Description |
|-------|------|-----------|-------------|
| `playerResources` | table | Yes | `playerColor -> { blood, victoryPoints }` |
| `destinationPerPlayerColor` | table | Yes | `playerColor -> destination` |
| `traitSettingsPerPlayer` | table | Yes | `playerColor -> { class -> count }` |
| `originDestinyActive` | table | Yes | `playerColor -> { activated, originName, ... }` |
| `draw2Pick1Active` | table | Yes | `playerColor -> bool` |
| `playAreaData` | table | No | `playerColor -> { center, size }` (recalculated) |

### API Cache (Persisted)

| Field | Type | Description |
|-------|------|-------------|
| `classes` | array | Raw class data from API |
| `customDice` | array | Dice type data from API |
| `runes` | array | Rune data from API |
| `referenceSheetUrl` | string | Reference sheet image URL |
| `ttsMenu.backgroundUrl` | string | Character select background |

### Lookup Tables (Rebuilt from cache)

| Field | Type | Description |
|-------|------|-------------|
| `classesByName` | table | `className -> classData` |
| `diceById` | table | `diceId -> diceData` |
| `runesById` | table | `runeId -> runeData` |
| `runesByType` | table | `{ class = [...], origin = [...] }` |

### Constants (Not persisted)

| Field | Description |
|-------|-------------|
| `PLAYERMAT_POSITIONS` | Spawn positions per player color |
| `NAVIGATE_OPTIONS` | Realm destination choices |
| `MARKET_SPIRIT_POSITIONS` | Spirit market slot positions |
| `SEAL_TARGET_COST` | Cost thresholds for sealing |

---

## Serialization

### What Gets Saved

`GameState.serialize()` returns JSON containing:

```lua
{
  -- Session
  fresh, gameStarted, gameId, navigationCount,

  -- Characters
  selectedCharacters,

  -- Per-player (survives undo)
  originDestinyActive,
  destinationPerPlayerColor,
  traitSettingsPerPlayer,
  draw2Pick1Active,
  playerResources,           -- blood, victoryPoints

  -- API cache (avoids re-fetch)
  classes, customDice, runes,
  characterMatData, availableCharacters,
  referenceSheetUrl, ttsMenu
}
```

### What Is NOT Saved

| Data | Location | Why Not Saved |
|------|----------|---------------|
| `matObject` | PlayerMatLib.state | TTS object reference (rebuilt on load) |
| `spirits` | PlayerMatLib.state | Rescanned from snap positions |
| `totals` | PlayerMatLib.state | Calculated from spirits |
| `playAreaData` | GameState | Recalculated from hand positions |
| Lookup tables | GameState | Rebuilt from cached arrays |

---

## onLoad / onSave Lifecycle

### onSave()

Called by TTS:
- Manual save
- Auto-save
- Rewind checkpoint (~every 10 seconds)
- Object enters container

```lua
function onSave()
  return GameState.serialize()  -- Returns JSON string
end
```

### onLoad(saveData)

Called by TTS:
- Game loads from save
- Rewind/undo
- All objects finished loading

```lua
function onLoad(saveData)
  GameState.deserialize(saveData)    -- Restore state from JSON
  drawPlayAreas()                     -- Recalculate play areas

  if GameState.gameStarted then
    if GameState.hasCachedData() then
      onCachedReload()               -- Fast path: use cache
    else
      getAssetData()                 -- Slow path: fetch API
    end
  else
    initializeLobby()                -- First load: fetch API
  end
end
```

### Flow Diagram

```
                    onLoad(saveData)
                          │
                          ▼
              GameState.deserialize()
                          │
                          ▼
                   drawPlayAreas()
                          │
                          ▼
               ┌─── gameStarted? ───┐
               │                    │
              Yes                   No
               │                    │
               ▼                    ▼
        hasCachedData()?      initializeLobby()
          │         │               │
         Yes        No              │
          │         │               ▼
          ▼         ▼          getAssetData()
   onCachedReload() getAssetData()  │
          │              │          │
          │              ▼          ▼
          │      onAssetLoadComplete()
          │              │
          ▼              ▼
   rebuildGameReferences()
          │
          ▼
   PlayerMatLib.registerPlayerMat()
          │
          ▼
   PlayerMatLib.rescanSpirits()
```

---

## API and Caching

### First Load (fresh = true)

1. `initializeLobby()` calls `getAssetData()`
2. `SupabaseLib.loadAssets()` makes HTTP request
3. Response parsed into `loadedData`
4. `onAssetLoadComplete(data)` called:
   - `GameState.buildLookups()` builds lookup tables
   - `AssetLoaderLib.preloadAllImages()` registers with `UI.setCustomAssets()`
   - `GameState.fresh = false`
   - UI created

### Reload with Cache (gameStarted = true, hasCachedData() = true)

1. `GameState.deserialize()` restores cached API data
2. `GameState.buildLookups()` rebuilds lookup tables
3. `onCachedReload()` skips HTTP:
   - Rebuilds UI
   - `rebuildGameReferences()` re-registers player mats
   - `PlayerMatLib.rescanSpirits()` rebuilds spirit tracking

### Cache Check

```lua
function GameState.hasCachedData()
  return GameState.classes and #GameState.classes > 0
end
```

### Why Cache Works

- `onSave()` persists `classes`, `customDice`, `runes`, etc.
- TTS saves this JSON in rewind checkpoints (~every 10 sec)
- `onLoad()` restores the cache via `deserialize()`
- No HTTP needed for undo/rewind

---

## PlayerMatLib State

PlayerMatLib maintains **transient** per-player state (not persisted):

```lua
state[playerColor] = {
  matGUID = "abc123",           -- For rebuilding reference
  matObject = <TTS Object>,     -- Live object (can't serialize)
  spirits = { [slot] = data },  -- Rebuilt by rescanSpirits()
  totals = { classes, origins } -- Calculated from spirits
}
```

**Persistent** player data lives in `GameState.playerResources`:

```lua
GameState.playerResources[playerColor] = {
  blood = 5,
  victoryPoints = 3
}
```

PlayerMatLib reads/writes through GameState:

```lua
function PlayerMatLib.getBlood(playerColor)
  return GameState.getPlayerResource(playerColor, "blood")
end

function PlayerMatLib.adjustBlood(playerColor, delta)
  local current = GameState.getPlayerResource(playerColor, "blood")
  GameState.setPlayerResource(playerColor, "blood", math.max(0, current + delta))
end
```
