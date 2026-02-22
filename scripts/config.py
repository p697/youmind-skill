"""
Configuration for Youmind Skill.
Centralizes constants, selectors, and local data paths.
"""

from pathlib import Path

# Paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
BROWSER_STATE_DIR = DATA_DIR / "browser_state"
BROWSER_PROFILE_DIR = BROWSER_STATE_DIR / "browser_profile"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
AUTH_INFO_FILE = DATA_DIR / "auth_info.json"
LIBRARY_FILE = DATA_DIR / "library.json"

# Youmind URLs
YOUMIND_BASE_URL = "https://youmind.com"
YOUMIND_SIGN_IN_URL = f"{YOUMIND_BASE_URL}/sign-in"
YOUMIND_OVERVIEW_URL = f"{YOUMIND_BASE_URL}/overview"
YOUMIND_BOARD_URL_PREFIX = f"{YOUMIND_BASE_URL}/boards/"

# Youmind selectors (ordered by reliability)
QUERY_INPUT_SELECTORS = [
    "textarea[placeholder*='Ask']",
    "textarea[placeholder*='question']",
    "textarea[aria-label*='Ask']",
    "textarea[aria-label*='question']",
    "div[contenteditable='true'][role='textbox']",
    "div[contenteditable='true']",
]

USER_MESSAGE_SELECTORS = [
    "div.ym-ask-user-content[data-user-message='true'][data-message-id]",
    "div.ym-ask-user-content[data-message-id]",
]

SEND_BUTTON_SELECTORS = [
    "button[aria-label*='Send']",
    "button[data-testid*='send']",
    "button[class*='send']",
]

RESPONSE_SELECTORS = [
    "div.ym-askai-container[data-pick-selection-message-id]",
    "div.ym-askai-container",
    "div.message-blocks",
    "div[class*='message-blocks']",
    "[class*='message-blocks']",
    "[data-message-author='assistant']",
    "[data-role='assistant']",
    "[data-testid*='assistant']",
    ".assistant-message",
    ".message.ai",
    ".message-content",
    "div[class*='message']",
    "[class*='message']",
]

THINKING_SELECTORS = [
    "div.thinking-message",
    "[data-testid*='thinking']",
]

# Browser configuration
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--no-first-run",
    "--no-default-browser-check",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Timeouts
LOGIN_TIMEOUT_MINUTES = 10
QUERY_TIMEOUT_SECONDS = 420
PAGE_LOAD_TIMEOUT = 30000
