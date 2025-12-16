# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

"Can't Stop" (贪骰无厌 2.0) is a QQ group dice game bot built with Python. The bot connects to NapCat (QQ bot framework) via WebSocket and features a PySide6 GM management interface.

## Commands

### Running the Application

```bash
# Start both QQ bot and GM GUI (recommended)
python start_game.py

# Start GM GUI only (standalone)
python gm/start_gamemaster.py
```

### Install Dependencies

```bash
pip install -r requirements.txt
# Core deps: aiohttp>=3.8.0, PySide6>=6.5.0
```

### Testing Individual Components

```bash
# Test command parser
python engine/command_parser.py

# Test board configuration
python game/board.py

# Test database schema
python database/schema.py
```

## Architecture

### Core Data Flow

```
QQ Message → QQBot (bot/qq_bot.py)
           → CommandParser (engine/command_parser.py)
           → GameEngine (engine/game_engine.py)
           → DAO Layer (database/dao.py)
           → SQLite (data/game.db)
```

### Key Components

**bot/qq_bot.py**: NapCat WebSocket client handling QQ group messages. Parses incoming messages, routes to CommandParser, executes via GameEngine, and sends responses.

**engine/command_parser.py**: Regex-based command parser with `PATTERNS` dict defining all game commands. Handles full-width/half-width punctuation normalization. `COMMAND_HANDLERS` maps command types to GameEngine methods.

**engine/game_engine.py**: Core game logic (~1500+ lines). Contains all gameplay methods: dice rolling, position management, item/trap/encounter handling, achievement tracking, duel system, contract system.

**engine/content_handler.py**: Handles encounters, items, and traps when players land on board cells.

**database/dao.py**: DAO classes (PlayerDAO, PositionDAO, InventoryDAO, GameStateDAO, ShopDAO, AchievementDAO, DailyLimitDAO, ContractDAO, GemPoolDAO) encapsulating all SQLite operations.

**database/models.py**: Dataclasses for Player, Position, PlayerGameState, ShopItem, etc. PlayerGameState has many effect flags (traps, items, encounters) stored as JSON in SQLite.

**database/schema.py**: Table creation and migration. Uses ALTER TABLE for schema evolution. `init_database()` creates/updates schema and initializes shop items.

**data/board_config.py**: Board layout definition. `BOARD_DATA` dict maps column numbers (3-18) to cell contents (Encounter/Item/Trap). `COLUMN_HEIGHTS` defines column lengths (3-10 cells).

**gui/gm_window.py**: PySide6 GM interface with BoardWidget for visual map display, player management, shop management, and game statistics.

### Game Mechanics

- **Board**: 16 columns (numbered 3-18), varying heights (3-10 cells)
- **Markers**: Players have temporary markers (3 max per round) and permanent markers
- **Win Condition**: Reach top of 3 columns
- **Cell Types**: E=Encounter, I=Item, T=Trap
- **Factions**: "收养人" (Adopter) or "Aeonreth" - affects item availability

### Configuration

`config.json` structure:
```json
{
  "websocket": {
    "url": "ws://127.0.0.1:3001",
    "access_token": "",
    "reconnect": true
  },
  "bot": {
    "allowed_groups": [],
    "admin_qq": ""
  },
  "database": {
    "path": "data/game.db"
  }
}
```

## Key Patterns

### Adding New Commands

1. Add regex pattern to `CommandParser.PATTERNS` in `engine/command_parser.py`
2. Add parameter extraction in `CommandParser._extract_params()`
3. Add handler mapping in `COMMAND_HANDLERS` dict
4. Implement method in `GameEngine` class

### Database Migrations

Schema changes use try/except pattern for backward compatibility:
```python
try:
    cursor.execute('ALTER TABLE game_state ADD COLUMN new_field INTEGER DEFAULT 0')
except sqlite3.OperationalError:
    pass  # Column already exists
```

### Game State Persistence

`PlayerGameState` class serializes complex state (lists, dicts) as JSON strings for SQLite storage via `to_dict()`/`from_dict()` methods.
