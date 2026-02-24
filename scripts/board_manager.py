#!/usr/bin/env python3
"""
Youmind board library management.
Stores board metadata and active board selection.
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def slugify(value: str) -> str:
    """Create a stable, CLI-friendly id."""
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "board"


def normalize_board_url(url: str) -> str:
    """
    Canonical board URL for library storage:
    - keep scheme/netloc/path
    - drop material-id/craft-id query context
    - keep any other query params
    - drop fragment
    """
    parsed = urlparse(url)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [
        (k, v)
        for (k, v) in query_items
        if k.lower() not in {"material-id", "craft-id"}
    ]
    new_query = urlencode(filtered, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))


class BoardLibrary:
    """Persists a local collection of Youmind boards."""

    def __init__(self):
        skill_dir = Path(__file__).parent.parent
        self.data_dir = skill_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.library_file = self.data_dir / "library.json"
        self.boards: Dict[str, Dict[str, Any]] = {}
        self.active_board_id: Optional[str] = None
        self._load_library()

    def _load_library(self):
        if not self.library_file.exists():
            self._save_library()
            return

        try:
            with open(self.library_file, "r") as f:
                data = json.load(f)
            self.boards = data.get("boards", data.get("notebooks", {}))
            self.active_board_id = data.get("active_board_id", data.get("active_notebook_id"))
            print(f"📚 Loaded board library with {len(self.boards)} boards")
        except Exception as e:
            print(f"⚠️ Error loading library.json: {e}")
            self.boards = {}
            self.active_board_id = None

    def _save_library(self):
        payload = {
            "boards": self.boards,
            "active_board_id": self.active_board_id,
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.library_file, "w") as f:
            json.dump(payload, f, indent=2)

    def find_board_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Find an existing board by exact URL."""
        target_url = normalize_board_url(url)
        for board in self.boards.values():
            if normalize_board_url(board.get("url", "")) == target_url:
                return board
        return None

    def _ensure_unique_id(self, base_id: str) -> str:
        if base_id not in self.boards:
            return base_id

        idx = 2
        while f"{base_id}-{idx}" in self.boards:
            idx += 1
        return f"{base_id}-{idx}"

    def add_board(
        self,
        url: str,
        name: str,
        description: str,
        topics: List[str],
        content_types: Optional[List[str]] = None,
        use_cases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_url = normalize_board_url(url)
        board_id = self._ensure_unique_id(slugify(name))

        board = {
            "id": board_id,
            "url": normalized_url,
            "name": name,
            "description": description,
            "topics": topics,
            "content_types": content_types or [],
            "use_cases": use_cases or [],
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "use_count": 0,
            "last_used": None,
        }

        self.boards[board_id] = board
        if len(self.boards) == 1:
            self.active_board_id = board_id

        self._save_library()
        print(f"✅ Added board: {name} ({board_id})")
        return board

    @staticmethod
    def _clean_discovery_answer(answer: str) -> str:
        marker = "EXTREMELY IMPORTANT: Is that ALL you need to know?"
        if marker in answer:
            answer = answer.split(marker, 1)[0]
        return answer.strip()

    @staticmethod
    def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
        """Try extracting a JSON object from plain text or fenced code block."""
        candidates = []

        fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S | re.I)
        candidates.extend(fenced)

        braces = re.findall(r"(\{.*\})", text, flags=re.S)
        candidates.extend(braces)

        for raw in candidates:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
        return None

    @staticmethod
    def _normalize_topics(raw_topics: Any) -> List[str]:
        if isinstance(raw_topics, list):
            parts = [str(x).strip() for x in raw_topics]
        elif isinstance(raw_topics, str):
            parts = [x.strip() for x in re.split(r"[,，;；\n]+", raw_topics)]
        else:
            parts = []

        seen = set()
        topics: List[str] = []
        for item in parts:
            if not item:
                continue
            normalized = item.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            topics.append(item)

        return topics

    @staticmethod
    def _looks_like_placeholder_name(name: str) -> bool:
        patterns = [
            r"^根据这个board",
            r"^我需要先查看",
            r"核心研究主题",
            r"^请阅读",
        ]
        if not name:
            return True
        if len(name) > 48:
            return True
        if name.endswith("："):
            return True
        return any(re.search(p, name) for p in patterns)

    @staticmethod
    def _looks_like_placeholder_description(description: str) -> bool:
        if not description:
            return True
        patterns = [
            r"^根据这个board",
            r"^我需要先查看",
        ]
        return any(re.search(p, description) for p in patterns)

    def _metadata_from_discovery(self, answer: str, board_url: str) -> Dict[str, Any]:
        """Generate structured metadata from a discovery answer."""
        answer = self._clean_discovery_answer(answer)
        payload = self._extract_json_block(answer)

        if payload:
            name = str(payload.get("name", "")).strip()
            description = str(payload.get("description", "")).strip()
            topics = self._normalize_topics(payload.get("topics"))
        else:
            name = ""
            description = ""
            topics = []

        if not description:
            lines = [line.strip() for line in answer.splitlines() if line.strip()]
            description = lines[0] if lines else "Youmind board discovered via Smart Add."

        if not name:
            # Try heading-like line from answer before falling back to URL suffix.
            lines = [line.strip(" -#*:\t") for line in answer.splitlines() if line.strip()]
            heading = next((line for line in lines if 2 <= len(line) <= 42), "")
            if heading:
                name = heading
            else:
                suffix = board_url.rstrip("/").split("/")[-1][:8]
                name = f"youmind-board-{suffix}"

        if not topics:
            # Extract English-ish terms as lightweight fallback.
            tokens = re.findall(r"[A-Za-z][A-Za-z0-9\\-]{2,}", answer)
            uniq: List[str] = []
            seen = set()
            for token in tokens:
                token_l = token.lower()
                if token_l in seen:
                    continue
                seen.add(token_l)
                uniq.append(token_l)
                if len(uniq) >= 6:
                    break
            topics = uniq if uniq else ["youmind", "board"]

        if self._looks_like_placeholder_name(name):
            english_topics = [t.lower() for t in topics if re.match(r"^[A-Za-z][A-Za-z0-9\\-]{1,}$", t)]
            if english_topics:
                name = "-".join(english_topics[:3]) + "-board"
            else:
                suffix = board_url.rstrip("/").split("/")[-1][:8]
                name = f"youmind-board-{suffix}"

        if self._looks_like_placeholder_description(description):
            lines = [line.strip(" -#*:\t") for line in answer.splitlines() if line.strip()]
            better_line = next(
                (
                    line
                    for line in lines
                    if not re.search(r"^根据这个board|^我需要先查看", line)
                    and len(line) >= 8
                ),
                "",
            )
            if better_line:
                description = better_line

        return {
            "name": name[:80],
            "description": description[:300],
            "topics": topics[:10],
        }

    def smart_add_board(
        self,
        url: str,
        show_browser: bool = False,
        activate: bool = True,
        prompt: Optional[str] = None,
        json_prompt: Optional[str] = None,
        single_pass: bool = True,
        allow_duplicate_url: bool = False,
    ) -> Dict[str, Any]:
        """
        Discover board content via chat and add it automatically.

        Default mode uses single-pass structured discovery (fast path).
        Optional two-pass mode:
        1) summary discovery
        2) strict JSON extraction
        """
        existing = self.find_board_by_url(url)
        if existing and not allow_duplicate_url:
            if activate:
                self.activate_board(existing["id"])
            return {
                "status": "exists",
                "board": existing,
                "discovery_answer": None,
                "metadata": None,
            }

        summary_prompt = (
            prompt
            or "请阅读当前board，简要总结：核心主题、资料类型、典型使用场景。输出简洁要点。"
        )

        # Local import to avoid circular import at module load time.
        from ask_question import ask_youmind

        summary_answer = None
        structured_answer = None

        def run_two_pass():
            nonlocal summary_answer, structured_answer
            summary_answer = ask_youmind(
                question=summary_prompt,
                board_url=url,
                headless=not show_browser,
            )
            if not summary_answer:
                raise RuntimeError("Smart Add discovery failed at pass 1 (summary).")
            summary_clean = self._clean_discovery_answer(summary_answer)
            summary_answer = summary_clean

            compact_summary = re.sub(r"\s+", " ", summary_clean).strip()[:1500]
            structured_prompt = (
                json_prompt
                or (
                    "请基于以下board摘要，严格输出JSON（不要任何额外文本）："
                    ' {"name":"简洁名称","description":"1-2句描述","topics":["主题1","主题2","主题3"]}\n'
                    f"摘要：{compact_summary}"
                )
            )
            structured_answer = ask_youmind(
                question=structured_prompt,
                board_url=url,
                headless=not show_browser,
            )
            if structured_answer:
                structured_clean = self._clean_discovery_answer(structured_answer)
                structured_answer = structured_clean
                payload = self._extract_json_block(structured_clean)
                if payload:
                    return self._metadata_from_discovery(structured_clean, url), "two_pass_json"
            return self._metadata_from_discovery(summary_clean, url), "two_pass_fallback_summary"

        if single_pass:
            structured_prompt = (
                json_prompt
                or '请阅读当前board，返回严格JSON（不要额外文字）：'
                ' {"name":"简洁名称","description":"1-2句描述","topics":["主题1","主题2","主题3"]}'
            )
            structured_answer = ask_youmind(
                question=structured_prompt,
                board_url=url,
                headless=not show_browser,
            )
            if structured_answer:
                structured_answer = self._clean_discovery_answer(structured_answer)
                metadata = self._metadata_from_discovery(structured_answer, url)
                if metadata.get("topics"):
                    discovery_used = "single_pass_structured"
                else:
                    metadata, discovery_used = run_two_pass()
                    discovery_used = "single_pass_then_" + discovery_used
            else:
                metadata, discovery_used = run_two_pass()
                discovery_used = "single_pass_then_" + discovery_used
        else:
            metadata, discovery_used = run_two_pass()

        if not metadata.get("topics"):
            raise RuntimeError("Smart Add failed: metadata topics are empty.")

        board = self.add_board(
            url=url,
            name=metadata["name"],
            description=metadata["description"],
            topics=metadata["topics"],
        )

        if activate:
            self.activate_board(board["id"])

        return {
            "status": "added",
            "board": board,
            "discovery_summary": summary_answer,
            "discovery_structured": structured_answer,
            "discovery_used": discovery_used,
            "metadata": metadata,
        }

    def remove_board(self, board_id: str) -> bool:
        if board_id not in self.boards:
            print(f"⚠️ Board not found: {board_id}")
            return False

        del self.boards[board_id]

        if self.active_board_id == board_id:
            self.active_board_id = next(iter(self.boards), None)

        self._save_library()
        print(f"✅ Removed board: {board_id}")
        return True

    def update_board(
        self,
        board_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        topics: Optional[List[str]] = None,
        content_types: Optional[List[str]] = None,
        use_cases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if board_id not in self.boards:
            raise ValueError(f"Board not found: {board_id}")

        board = self.boards[board_id]

        if name is not None:
            board["name"] = name
        if description is not None:
            board["description"] = description
        if topics is not None:
            board["topics"] = topics
        if content_types is not None:
            board["content_types"] = content_types
        if use_cases is not None:
            board["use_cases"] = use_cases
        if tags is not None:
            board["tags"] = tags
        if url is not None:
            board["url"] = url

        board["updated_at"] = datetime.now().isoformat()

        self._save_library()
        print(f"✅ Updated board: {board['name']}")
        return board

    def get_board(self, board_id: str) -> Optional[Dict[str, Any]]:
        return self.boards.get(board_id)

    def list_boards(self) -> List[Dict[str, Any]]:
        return list(self.boards.values())

    def search_boards(self, query: str) -> List[Dict[str, Any]]:
        q = query.lower()
        matches = []

        for board in self.boards.values():
            fields = [
                board["name"].lower(),
                board["description"].lower(),
                " ".join(board["topics"]).lower(),
                " ".join(board["tags"]).lower(),
                " ".join(board.get("use_cases", [])).lower(),
            ]
            if any(q in field for field in fields):
                matches.append(board)

        return matches

    def activate_board(self, board_id: str) -> Dict[str, Any]:
        if board_id not in self.boards:
            raise ValueError(f"Board not found: {board_id}")

        self.active_board_id = board_id
        self._save_library()

        board = self.boards[board_id]
        print(f"✅ Activated board: {board['name']}")
        return board

    def get_active_board(self) -> Optional[Dict[str, Any]]:
        if not self.active_board_id:
            return None
        return self.boards.get(self.active_board_id)

    def increment_use_count(self, board_id: str) -> Dict[str, Any]:
        if board_id not in self.boards:
            raise ValueError(f"Board not found: {board_id}")

        board = self.boards[board_id]
        board["use_count"] += 1
        board["last_used"] = datetime.now().isoformat()
        self._save_library()
        return board

    def get_stats(self) -> Dict[str, Any]:
        total_boards = len(self.boards)
        topics = set()
        total_use_count = 0

        for board in self.boards.values():
            topics.update(board["topics"])
            total_use_count += board["use_count"]

        most_used = None
        if self.boards:
            most_used = max(self.boards.values(), key=lambda x: x["use_count"])

        return {
            "total_boards": total_boards,
            "total_topics": len(topics),
            "total_use_count": total_use_count,
            "active_board": self.get_active_board(),
            "most_used_board": most_used,
            "library_path": str(self.library_file),
        }

    def export_library(self, output_path: Optional[str] = None, include_auth: bool = False) -> str:
        """Export board library to a JSON file."""
        import json
        from datetime import datetime

        # Default filename with timestamp
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            output_path = f"youmind-library-{timestamp}.json"

        # Prepare export data
        export_data = {
            "export_version": "1.0",
            "export_date": datetime.now().isoformat(),
            "exported_from": str(self.library_file),
            "boards": self.boards,
            "active_board_id": self.active_board_id,
            "stats": self.get_stats(),
        }

        # Optionally include auth metadata (without sensitive state)
        if include_auth:
            auth_file = self.data_dir / "auth_info.json"
            if auth_file.exists():
                try:
                    with open(auth_file, "r") as f:
                        auth_data = json.load(f)
                    # Only include metadata, not cookies/state
                    export_data["auth_metadata"] = {
                        "authenticated": auth_data.get("authenticated", False),
                        "user_id": auth_data.get("user_id"),
                        "email": auth_data.get("email"),
                        "auth_date": auth_data.get("date"),
                    }
                except Exception:
                    pass

        # Write to file
        output_file = Path(output_path)
        with open(output_file, "w") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Exported {len(self.boards)} boards to: {output_file.absolute()}")
        return str(output_file.absolute())

    def import_library(
        self,
        input_path: str,
        merge: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Import board library from a JSON file."""
        import json
        from datetime import datetime

        input_file = Path(input_path)
        if not input_file.exists():
            raise FileNotFoundError(f"Import file not found: {input_path}")

        # Load import data
        with open(input_file, "r") as f:
            import_data = json.load(f)

        # Validate format
        if "boards" not in import_data:
            raise ValueError("Invalid import file: missing 'boards' field")

        imported_boards = import_data.get("boards", {})
        imported_active_id = import_data.get("active_board_id")

        # Calculate changes
        stats = {
            "existing_boards": len(self.boards),
            "imported_boards": len(imported_boards),
            "new_boards": 0,
            "updated_boards": 0,
            "conflicts": [],
        }

        # Check for conflicts/duplicates
        for board_id, board_data in imported_boards.items():
            if board_id in self.boards:
                stats["conflicts"].append(board_id)
                if merge:
                    stats["updated_boards"] += 1
            else:
                stats["new_boards"] += 1

        if dry_run:
            print("\n📋 Dry Run Preview:")
            print(f"  - Existing boards: {stats['existing_boards']}")
            print(f"  - Boards to import: {stats['imported_boards']}")
            print(f"  - New boards: {stats['new_boards']}")
            print(f"  - Conflicts (same ID): {len(stats['conflicts'])}")
            if merge and stats["conflicts"]:
                print(f"  - Will update conflicts: Yes")
            elif stats["conflicts"]:
                print(f"  - Will skip conflicts: Yes")
            return stats

        # Apply import
        if merge:
            # Merge: add new boards, update existing
            for board_id, board_data in imported_boards.items():
                self.boards[board_id] = board_data
            print(f"✅ Merged {len(imported_boards)} boards (added {stats['new_boards']}, updated {stats['updated_boards']})")
        else:
            # Replace: clear existing and add imported (except conflicts)
            original_count = len(self.boards)
            added = 0
            skipped = 0
            for board_id, board_data in imported_boards.items():
                if board_id in self.boards:
                    skipped += 1
                    continue
                self.boards[board_id] = board_data
                added += 1
            print(f"✅ Imported {added} new boards (skipped {skipped} existing)")

        # Set active board if not already set
        if imported_active_id and not self.active_board_id:
            if imported_active_id in self.boards:
                self.active_board_id = imported_active_id
                print(f"✅ Set active board: {imported_active_id}")

        self._save_library()
        return stats


def main():
    parser = argparse.ArgumentParser(description="Manage Youmind board library")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    add_parser = subparsers.add_parser("add", help="Add a board")
    add_parser.add_argument("--url", required=True, help="Youmind board URL")
    add_parser.add_argument("--name", required=True, help="Display name")
    add_parser.add_argument("--description", required=True, help="Description")
    add_parser.add_argument("--topics", required=True, help="Comma-separated topics")
    add_parser.add_argument("--use-cases", help="Comma-separated use cases")
    add_parser.add_argument("--tags", help="Comma-separated tags")

    smart_add_parser = subparsers.add_parser(
        "smart-add",
        help="Auto-discover metadata via board chat and add board",
    )
    smart_add_parser.add_argument("--url", required=True, help="Youmind board URL")
    smart_add_parser.add_argument("--show-browser", action="store_true", help="Show browser for discovery")
    smart_add_parser.add_argument("--prompt", help="Custom summary prompt (pass 1)")
    smart_add_parser.add_argument("--json-prompt", help="Custom JSON prompt (pass 2)")
    smart_add_parser.add_argument(
        "--single-pass",
        dest="single_pass",
        action="store_true",
        help="Use one-pass structured discovery (default)",
    )
    smart_add_parser.add_argument(
        "--two-pass",
        dest="single_pass",
        action="store_false",
        help="Use two-pass discovery (summary + structured extraction)",
    )
    smart_add_parser.set_defaults(single_pass=True)
    smart_add_parser.add_argument("--no-activate", action="store_true", help="Do not set new board as active")
    smart_add_parser.add_argument(
        "--allow-duplicate-url",
        action="store_true",
        help="Allow adding even when URL already exists",
    )

    subparsers.add_parser("list", help="List boards")

    search_parser = subparsers.add_parser("search", help="Search boards")
    search_parser.add_argument("--query", required=True, help="Search query")

    activate_parser = subparsers.add_parser("activate", help="Set active board")
    activate_parser.add_argument("--id", required=True, help="Board ID")

    remove_parser = subparsers.add_parser("remove", help="Remove a board")
    remove_parser.add_argument("--id", required=True, help="Board ID")

    subparsers.add_parser("stats", help="Show statistics")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export board library to a file")
    export_parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: youmind-library-YYYYMMDD-HHMMSS.json)",
    )
    export_parser.add_argument(
        "--include-auth",
        action="store_true",
        help="Include authentication metadata (default: False for security)",
    )

    # Import command
    import_parser = subparsers.add_parser("import", help="Import board library from a file")
    import_parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Input file path to import",
    )
    import_parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge with existing library instead of replacing",
    )
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying",
    )

    args = parser.parse_args()
    library = BoardLibrary()

    if args.command == "add":
        topics = [x.strip() for x in args.topics.split(",") if x.strip()]
        use_cases = [x.strip() for x in args.use_cases.split(",") if x.strip()] if args.use_cases else None
        tags = [x.strip() for x in args.tags.split(",") if x.strip()] if args.tags else None

        board = library.add_board(
            url=args.url,
            name=args.name,
            description=args.description,
            topics=topics,
            use_cases=use_cases,
            tags=tags,
        )
        print(json.dumps(board, indent=2))

    elif args.command == "smart-add":
        result = library.smart_add_board(
            url=args.url,
            show_browser=args.show_browser,
            activate=not args.no_activate,
            prompt=args.prompt,
            json_prompt=args.json_prompt,
            single_pass=args.single_pass,
            allow_duplicate_url=args.allow_duplicate_url,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "list":
        boards = library.list_boards()
        if not boards:
            print("📚 Board library is empty. Add one with board_manager.py add")
            return

        print("\n📚 Board Library:")
        for board in boards:
            active = " [ACTIVE]" if board["id"] == library.active_board_id else ""
            print(f"\n  🧠 {board['name']}{active}")
            print(f"     ID: {board['id']}")
            print(f"     Topics: {', '.join(board['topics'])}")
            print(f"     Uses: {board['use_count']}")

    elif args.command == "search":
        matches = library.search_boards(args.query)
        if not matches:
            print(f"🔍 No boards found for: {args.query}")
            return

        print(f"\n🔍 Found {len(matches)} board(s):")
        for board in matches:
            print(f"\n  🧠 {board['name']} ({board['id']})")
            print(f"     {board['description']}")

    elif args.command == "activate":
        board = library.activate_board(args.id)
        print(f"Now using: {board['name']}")

    elif args.command == "remove":
        if library.remove_board(args.id):
            print("Board removed")

    elif args.command == "stats":
        stats = library.get_stats()
        print("\n📊 Library Statistics:")
        print(f"  Total boards: {stats['total_boards']}")
        print(f"  Total topics: {stats['total_topics']}")
        print(f"  Total uses: {stats['total_use_count']}")
        if stats["active_board"]:
            print(f"  Active: {stats['active_board']['name']}")
        if stats["most_used_board"]:
            print(f"  Most used: {stats['most_used_board']['name']} ({stats['most_used_board']['use_count']} uses)")
        print(f"  Library path: {stats['library_path']}")

    elif args.command == "export":
        try:
            output_file = library.export_library(
                output_path=args.output,
                include_auth=args.include_auth,
            )
            print(f"\n💡 Import with:")
            print(f"  python scripts/run.py board_manager.py import -i '{output_file}'")
        except Exception as e:
            print(f"❌ Export failed: {e}")
            return 1

    elif args.command == "import":
        try:
            stats = library.import_library(
                input_path=args.input,
                merge=args.merge,
                dry_run=args.dry_run,
            )
            if args.dry_run:
                print("\n⚠️ Dry run - no changes made. Run without --dry-run to apply.")
        except FileNotFoundError as e:
            print(f"❌ Import failed: {e}")
            return 1
        except ValueError as e:
            print(f"❌ Import failed: {e}")
            return 1
        except Exception as e:
            print(f"❌ Import failed: {e}")
            return 1

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
