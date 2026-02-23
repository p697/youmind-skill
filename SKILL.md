---
name: youmind
description: Use this skill to query Youmind boards directly from Claude/Codex via browser automation, with persistent authentication and a local board library. Supports board Q&A and adding links/materials to a board via chat actions. Trigger when users mention Youmind, share a board URL (https://youmind.com/boards/...), ask to chat with board materials, ask to save/add a link into a board, or request board management.
---

# Youmind Research Assistant Skill

Interact with Youmind board chat from CLI tools through browser automation. Each query opens a fresh browser session, asks one question, returns the answer, then closes.

## Critical Rule: Always Use `run.py`

Never call scripts directly. Always run:

```bash
python scripts/run.py [script].py [args...]
```

Examples:

```bash
python scripts/run.py auth_manager.py status
python scripts/run.py board_manager.py list
python scripts/run.py ask_question.py --question "..."
```

## Workflow

### 0. Smart Add (Recommended)

One-command smart add:

```bash
python scripts/run.py board_manager.py smart-add \
  --url "https://youmind.com/boards/..."
```

`smart-add` defaults to two-pass discovery (summary -> structured JSON).
If needed, force one-pass:

```bash
python scripts/run.py board_manager.py smart-add \
  --url "https://youmind.com/boards/..." \
  --single-pass
```

If auto-discovery quality is poor for a specific board, use two-step fallback:

```bash
# Step 1: Discover board content
python scripts/run.py ask_question.py \
  --question "请简要概括这个board的内容、主题与典型使用场景" \
  --board-url "https://youmind.com/boards/..."

# Step 2: Add using discovered metadata
python scripts/run.py board_manager.py add \
  --url "https://youmind.com/boards/..." \
  --name "Based on discovered content" \
  --description "Based on discovered content" \
  --topics "topic1,topic2"
```

### 1. Check Authentication

```bash
python scripts/run.py auth_manager.py status
python scripts/run.py auth_manager.py validate
```

If unauthenticated or invalid, run setup.

### 2. Setup Authentication (One-Time)

```bash
python scripts/run.py auth_manager.py setup
```

Important:
- Browser should be visible.
- User must complete Youmind login manually.
- Auth state is saved under `data/browser_state/`.

### 3. Manage Board Library

```bash
# List boards
python scripts/run.py board_manager.py list

# Add board (all required)
python scripts/run.py board_manager.py add \
  --url "https://youmind.com/boards/..." \
  --name "Board name" \
  --description "What this board contains" \
  --topics "topic1,topic2"

# Search boards
python scripts/run.py board_manager.py search --query "topic"

# Activate board
python scripts/run.py board_manager.py activate --id board-id

# Remove board
python scripts/run.py board_manager.py remove --id board-id
```

### 4. Ask Board Chat

```bash
# Use active board
python scripts/run.py ask_question.py --question "Your question"

# Use specific board by ID
python scripts/run.py ask_question.py --question "..." --board-id board-id

# Use board URL directly
python scripts/run.py ask_question.py --question "..." --board-url "https://youmind.com/boards/..."

# Show browser for debugging
python scripts/run.py ask_question.py --question "..." --show-browser
```

Board URL context rule:
- If user provides a board URL with `material-id` / `craft-id`, do NOT always keep it.
- Default behavior: ignore these IDs and run a board-level query.
- Keep these IDs only when user intent explicitly requires current material context, e.g.:
  - "读一下当前文章"
  - "基于当前素材继续分析"
  - "summarize this current material"

### 5. Add Material to a Board (Supported)

This skill can add URLs/materials to a Youmind board by issuing an explicit save command through board chat.

Use this when user says things like:
- "把这个链接加到这个board"
- "保存这个网页到YouMind"
- "add this URL to my board"

Recommended execution pattern (single-pass, fast path):

```bash
# Send a strict add-only command
python scripts/run.py ask_question.py \
  --board-url "https://youmind.com/boards/..." \
  --question "只执行一个动作：把这个链接添加到当前board资料库 https://example.com 。不要总结，不要列清单。完成后只回复：ADD_OK。"
```

Important:
- This is a chat-driven write action (not an official add API).
- Prefer single-pass result parsing for speed/token savings.
- Treat it as success if response contains clear success markers like:
  - `ADD_OK`
  - `资料已保存`
  - `资料已添加`
- Only run a second verification ask if the reply is ambiguous or indicates failure.
- If needed, retry once with `--show-browser`.

## Follow-Up Rule

Every answer appends a reminder asking whether information is complete.

Required behavior:
1. Compare answer vs original user task.
2. If gaps exist, immediately ask one or more follow-up questions.
3. Include enough context in each follow-up because queries are stateless.
4. Synthesize all answers before replying to the user.

## Script Reference

### `auth_manager.py`

```bash
python scripts/run.py auth_manager.py setup
python scripts/run.py auth_manager.py status
python scripts/run.py auth_manager.py validate
python scripts/run.py auth_manager.py reauth
python scripts/run.py auth_manager.py clear
```

### `board_manager.py`

```bash
python scripts/run.py board_manager.py add --url URL --name NAME --description DESC --topics TOPICS
python scripts/run.py board_manager.py list
python scripts/run.py board_manager.py search --query QUERY
python scripts/run.py board_manager.py activate --id ID
python scripts/run.py board_manager.py remove --id ID
python scripts/run.py board_manager.py stats
```

### `ask_question.py`

```bash
python scripts/run.py ask_question.py --question "..." [--board-id ID] [--board-url URL] [--show-browser]
# Optional long-wait override for slow boards
python scripts/run.py ask_question.py --question "..." --timeout-seconds 420
```

### `cleanup_manager.py`

```bash
python scripts/run.py cleanup_manager.py
python scripts/run.py cleanup_manager.py --confirm
python scripts/run.py cleanup_manager.py --confirm --preserve-library
```

## Data Storage

All local data is saved in:

```text
data/
├── library.json          # Board library and active board
├── auth_info.json        # Authentication metadata
└── browser_state/
    └── state.json        # Browser cookies and storage state
```

Never commit `data/`.

## Environment

The first `run.py` execution auto-creates `.venv` and installs dependencies.

Manual fallback:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m patchright install chrome
```

## Known Limitations

- Stateless query model: no persistent chat thread context.
- UI selectors can change as Youmind updates their frontend.
- Requires valid Youmind login for private board access.
- "Add material" is best-effort through chat instructions, not a dedicated Youmind write API.

## Resources

- `references/api_reference.md`
- `references/troubleshooting.md`
- `references/usage_patterns.md`
- `AUTHENTICATION.md`
