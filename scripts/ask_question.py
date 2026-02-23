#!/usr/bin/env python3
"""
Simple Youmind question interface (stateless mode).
Each question opens a fresh browser context, asks once, then exits.
"""

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from patchright.sync_api import sync_playwright

# Add scripts directory to import path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from board_manager import BoardLibrary
from browser_utils import BrowserFactory, StealthUtils
from config import (
    QUERY_TIMEOUT_SECONDS,
    QUERY_INPUT_SELECTORS,
    RESPONSE_SELECTORS,
    SEND_BUTTON_SELECTORS,
    THINKING_SELECTORS,
    USER_MESSAGE_SELECTORS,
    YOUMIND_BOARD_URL_PREFIX,
)

FOLLOW_UP_REMINDER = (
    "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know? "
    "Before replying to the user, compare this answer with the original request. "
    "If details are missing, ask another comprehensive follow-up question and include full context."
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _question_needs_context_id(question: str) -> bool:
    """Heuristic: keep material/craft id only when user asks current material context."""
    q = _normalize_text(question).lower()
    context_keywords = [
        "当前文章",
        "当前素材",
        "这篇文章",
        "这条素材",
        "当前内容",
        "当前卡片",
        "material",
        "craft",
        "current article",
        "current material",
        "this article",
        "this material",
    ]
    return any(token in q for token in context_keywords)


def _strip_context_ids(board_url: str) -> str:
    """Remove material-id/craft-id from a board URL while keeping other query params."""
    parsed = urlparse(board_url)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [
        (k, v)
        for (k, v) in query_items
        if k.lower() not in {"material-id", "craft-id"}
    ]
    new_query = urlencode(filtered, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))


def _resolve_effective_board_url(board_url: str, question: str) -> str:
    """Default to board-level URL unless question explicitly needs material/craft context."""
    parsed = urlparse(board_url)
    query_keys = {k.lower() for (k, _) in parse_qsl(parsed.query, keep_blank_values=True)}
    has_context_id = any(key in {"material-id", "craft-id"} for key in query_keys)
    if not has_context_id:
        return board_url
    if _question_needs_context_id(question):
        return board_url
    return _strip_context_ids(board_url)


def _is_same_question(user_text: str, question: str) -> bool:
    """Robust match between rendered user message and the submitted question."""
    user_norm = _normalize_text(user_text)
    question_norm = _normalize_text(question)

    if not user_norm or not question_norm:
        return False
    if question_norm in user_norm:
        return True

    # Strong signal: long alnum token (e.g., request IDs, explicit markers).
    strong_tokens = re.findall(r"[A-Za-z0-9_-]{5,}", question_norm)
    for token in strong_tokens:
        if token in user_norm:
            return True

    # Fallback for punctuation/formatting drift.
    user_compact = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", user_norm).lower()
    question_compact = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", question_norm).lower()
    if not user_compact or not question_compact:
        return False
    if question_compact in user_compact:
        return True
    if len(question_compact) >= 10 and question_compact[-10:] in user_compact:
        return True

    return False


def _looks_like_metadata_json(text: str) -> bool:
    compact = _normalize_text(text).lower()
    return (
        "\"name\"" in compact
        and "\"description\"" in compact
        and "\"topics\"" in compact
    )


def _question_requests_json(question: str) -> bool:
    q = _normalize_text(question).lower()
    return "json" in q or "结构化" in q or "严格输出" in q


def _collect_messages(
    page,
    selectors: List[str],
    id_attrs: List[str],
    require_id: bool = False,
) -> List[Dict[str, str]]:
    """Collect message-like nodes from the first matching selector in DOM order."""
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
            selector_messages: List[Dict[str, str]] = []

            for idx, el in enumerate(elements):
                text = _normalize_text(el.inner_text() or "")
                if not text:
                    continue

                msg_id = ""
                for attr in id_attrs:
                    value = el.get_attribute(attr)
                    if value:
                        msg_id = value
                        break
                if require_id and not msg_id:
                    continue
                if not msg_id:
                    msg_id = f"{selector}:{idx}"

                selector_messages.append({"id": msg_id, "text": text})

            if selector_messages:
                return selector_messages
        except Exception:
            continue

    return []


def _collect_responses(page) -> List[Dict[str, str]]:
    """Collect assistant response nodes."""
    return _collect_messages(
        page,
        RESPONSE_SELECTORS,
        ["data-pick-selection-message-id", "data-message-id"],
        require_id=True,
    )


def _collect_user_messages(page) -> List[Dict[str, str]]:
    """Collect user message nodes."""
    return _collect_messages(
        page,
        USER_MESSAGE_SELECTORS,
        ["data-message-id", "data-pick-selection-message-id"],
        require_id=True,
    )


def _collect_conversation_sequence(page) -> List[Dict[str, str]]:
    """Collect user/assistant messages in DOM order."""
    selector = (
        "div.ym-ask-user-content[data-user-message='true'][data-message-id], "
        "div.ym-ask-user-content[data-message-id], "
        "div.ym-askai-container[data-pick-selection-message-id], "
        "div.ym-askai-container[data-message-id]"
    )
    sequence: List[Dict[str, str]] = []

    try:
        elements = page.query_selector_all(selector)
    except Exception:
        return sequence

    for el in elements:
        try:
            text = _normalize_text(el.inner_text() or "")
            if not text:
                continue

            class_name = el.get_attribute("class") or ""
            is_assistant = "ym-askai-container" in class_name
            msg_type = "assistant" if is_assistant else "user"

            msg_id = (
                el.get_attribute("data-pick-selection-message-id")
                or el.get_attribute("data-message-id")
            )
            if not msg_id:
                continue

            sequence.append({"type": msg_type, "id": msg_id, "text": text})
        except Exception:
            continue

    return sequence


def _is_thinking(page) -> bool:
    """Best-effort detection for in-progress generation."""
    for selector in THINKING_SELECTORS:
        try:
            nodes = page.query_selector_all(selector)
            if any(node.is_visible() for node in nodes):
                return True
        except Exception:
            continue
    return False


def _find_input_selector(page) -> Optional[str]:
    """Return the first usable chat input selector."""
    for selector in QUERY_INPUT_SELECTORS:
        try:
            page.wait_for_selector(selector, timeout=5000, state="visible")
            return selector
        except Exception:
            continue
    return None


def ask_youmind(
    question: str,
    board_url: str,
    headless: bool = True,
    timeout_seconds: int = QUERY_TIMEOUT_SECONDS,
) -> Optional[str]:
    """Send a question to a Youmind board chat and return the answer."""
    auth = AuthManager()
    if not auth.is_authenticated():
        print("⚠️ Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    effective_board_url = _resolve_effective_board_url(board_url, question)
    print(f"💬 Asking: {question}")
    print(f"🧠 Board: {effective_board_url}")
    if effective_board_url != board_url:
        print("  ℹ️ Ignoring material/craft context id for board-level query")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=headless)

        page = context.new_page()
        print("  🌐 Opening board...")
        page.goto(effective_board_url, wait_until="domcontentloaded")

        # If redirected to sign-in, auth is invalid.
        if "youmind.com" not in page.url or "sign-in" in page.url:
            print("  ❌ Redirected to sign-in. Authentication may be expired.")
            return None

        # Snapshot previous conversation to ensure we only return post-submit output.
        previous_sequence = _collect_conversation_sequence(page)
        previous_user_ids = [
            msg["id"] for msg in previous_sequence if msg.get("type") == "user"
        ]
        baseline_max_user_id = max(previous_user_ids) if previous_user_ids else ""
        previous_assistant_text_set = {
            msg["text"] for msg in previous_sequence if msg.get("type") == "assistant"
        }
        normalized_question = _normalize_text(question)
        expects_json = _question_requests_json(normalized_question)

        input_selector = _find_input_selector(page)
        if not input_selector:
            print("  ❌ Could not find chat input")
            return None

        print(f"  ✓ Found chat input: {input_selector}")
        StealthUtils.realistic_click(page, input_selector)
        StealthUtils.human_type(page, input_selector, question)

        # Submit question via Enter first.
        print("  📤 Submitting question...")
        page.keyboard.press("Enter")

        # Some editors insert newline on Enter; click Send button as fallback.
        time.sleep(0.6)
        for send_selector in SEND_BUTTON_SELECTORS:
            try:
                if StealthUtils.realistic_click(page, send_selector):
                    break
            except Exception:
                continue

        print("  ⏳ Waiting for answer...")

        submit_started_at = time.time()
        deadline = submit_started_at + max(30, int(timeout_seconds))
        stable_count = 0
        last_candidate_id: Optional[str] = None
        last_text = None
        target_user_id: Optional[str] = None
        target_user_is_question_match = False

        while time.time() < deadline:
            conversation = _collect_conversation_sequence(page)
            candidate = None
            candidate_id = None
            elapsed = time.time() - submit_started_at

            if conversation:
                users = [msg for msg in conversation if msg.get("type") == "user"]
                assistants = [msg for msg in conversation if msg.get("type") == "assistant"]

                # Primary path: newest user turn that matches this exact question.
                matching_user_ids = [
                    msg["id"]
                    for msg in users
                    if normalized_question and _is_same_question(msg["text"], normalized_question)
                ]
                if matching_user_ids:
                    newest_match = max(matching_user_ids)
                    if newest_match > baseline_max_user_id:
                        target_user_id = newest_match
                        target_user_is_question_match = True

                # Fallback: if exact match can't be found, use latest user turn after submit.
                if target_user_id is None and elapsed >= 20:
                    post_submit_user_ids = [
                        msg["id"] for msg in users if msg["id"] > baseline_max_user_id
                    ]
                    if post_submit_user_ids:
                        target_user_id = max(post_submit_user_ids)

                if target_user_id is not None:
                    post_target_assistants = sorted(
                        [msg for msg in assistants if msg["id"] > target_user_id],
                        key=lambda x: x["id"],
                    )
                    for assistant_msg in post_target_assistants:
                        assistant_text = assistant_msg["text"]
                        if not assistant_text:
                            continue
                        if _looks_like_metadata_json(assistant_text) and not expects_json:
                            continue
                        if (
                            not target_user_is_question_match
                            and assistant_text in previous_assistant_text_set
                            and elapsed < 20
                        ):
                            continue
                        candidate = assistant_text
                        candidate_id = assistant_msg["id"]
                        break

            if candidate:
                if candidate_id == last_candidate_id and candidate == last_text:
                    stable_count += 1
                    if stable_count >= 2 and elapsed >= 3:
                        print("  ✅ Got answer")
                        return candidate + FOLLOW_UP_REMINDER
                else:
                    last_candidate_id = candidate_id
                    last_text = candidate
                    stable_count = 1

            # Thinking state is informative but not blocking; keep polling text.
            if _is_thinking(page):
                time.sleep(0.8)
                continue

            time.sleep(0.8)

        print(f"  ❌ Timeout waiting for answer ({max(30, int(timeout_seconds))}s)")
        return None

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None

    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


def _resolve_board_url(board_url: Optional[str], board_id: Optional[str]) -> Optional[str]:
    if board_url:
        return board_url

    library = BoardLibrary()

    if board_id:
        board = library.get_board(board_id)
        if not board:
            print(f"❌ Board '{board_id}' not found")
            return None
        return board["url"]

    active = library.get_active_board()
    if active:
        print(f"🧠 Using active board: {active['name']}")
        return active["url"]

    boards = library.list_boards()
    if boards:
        print("\n🧠 Available boards:")
        for b in boards:
            mark = " [ACTIVE]" if b["id"] == library.active_board_id else ""
            print(f"  {b['id']}: {b['name']}{mark}")
        print("\nSpecify with --board-id or set active:")
        print("python scripts/run.py board_manager.py activate --id ID")
    else:
        print("❌ No boards in library. Add one first:")
        print("python scripts/run.py board_manager.py add --url URL --name NAME --description DESC --topics TOPICS")

    return None


def main():
    parser = argparse.ArgumentParser(description="Ask Youmind board chat a question")
    parser.add_argument("--question", required=True, help="Question to ask")
    parser.add_argument("--board-url", help="Youmind board URL")
    parser.add_argument("--board-id", help="Board ID from local library")
    parser.add_argument("--show-browser", action="store_true", help="Show browser for debugging")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=QUERY_TIMEOUT_SECONDS,
        help=f"Max time to wait for answer (default: {QUERY_TIMEOUT_SECONDS})",
    )
    args = parser.parse_args()

    board_url = _resolve_board_url(args.board_url, args.board_id)
    if not board_url:
        return 1

    if not board_url.startswith(YOUMIND_BOARD_URL_PREFIX):
        print(f"⚠️ Board URL should start with: {YOUMIND_BOARD_URL_PREFIX}")

    answer = ask_youmind(
        question=args.question,
        board_url=board_url,
        headless=not args.show_browser,
        timeout_seconds=args.timeout_seconds,
    )

    if not answer:
        print("\n❌ Failed to get answer")
        return 1

    print("\n" + "=" * 60)
    print(f"Question: {args.question}")
    print("=" * 60)
    print()
    print(answer)
    print()
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
