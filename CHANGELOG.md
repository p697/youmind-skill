# Changelog

All notable changes to this project are documented here.

## [2.1.0] - 2026-02-24

### Added
- **Board library export/import** functionality in `board_manager.py`
  - `export` command: Backup library to JSON with timestamp
  - `import` command: Restore library from JSON with merge/replace options
  - `--dry-run` flag for safe import preview
  - `--include-auth` option for cross-device migration
- Comprehensive error handling for import operations (FileNotFound, ValueError)

### Changed
- Updated `SKILL.md` with export/import workflow documentation

## [2.0.0] - 2026-02-22

### Added
- **Youmind adaptation** of the original NotebookLM skill architecture
- New `board_manager.py` for Youmind board library management
- New `board_manager.py smart-add` workflow with two-pass discovery and fallback parsing

### Changed
- Reworked `ask_question.py` from NotebookLM notebook flow to Youmind board chat flow
- Reworked `auth_manager.py` for Youmind sign-in and validation routes
- Updated `config.py` selectors and URL constants for Youmind
- Updated `SKILL.md`, `README.md`, and `references/*` to Youmind terminology/workflow
- Updated `run.py` command guidance to `board_manager.py`

### Fixed
- Added missing `random_mouse_movement` utility used by `browser_session.py`
- Aligned browser install target to Chrome in `scripts/__init__.py`

## [1.3.0] - 2025-11-21

### Added
- Modular architecture refactor (`config.py`, `browser_utils.py`)

### Changed
- Query timeout increased to 120 seconds

### Fixed
- Thinking-message detection and response stability polling
- NotebookLM selector updates for then-current UI

## [1.2.0] - 2025-10-28

### Added
- Initial public release
- NotebookLM browser automation integration
