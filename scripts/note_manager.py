"""
note_manager.py — manage YouMind notes and craft documents via API

Commands:
  create        Create a new note (type: note) with plain text content
  get           Get a note by ID
  list          List all notes in the space
  create-craft  Create a craft document (type: page) with plain text content
"""

import argparse
import json
import sys

from api_client import YoumindApiClient, ApiError, AuthError


def cmd_create(args: argparse.Namespace) -> None:
    api = YoumindApiClient()
    result = api.create_note(
        content_plain=args.content,
        title=args.title or None,
        board_id=args.board_id or None,
        gen_title=args.gen_title,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_get(args: argparse.Namespace) -> None:
    api = YoumindApiClient()
    result = api.get_note(args.id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_list(args: argparse.Namespace) -> None:
    api = YoumindApiClient()
    result = api.list_notes()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_create_craft(args: argparse.Namespace) -> None:
    api = YoumindApiClient()
    result = api.create_craft(
        board_id=args.board_id,
        content_plain=args.content,
        title=args.title or None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage YouMind notes and craft documents via API"
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    # create (note)
    p_create = subparsers.add_parser("create", help="Create a new note (type: note)")
    p_create.add_argument("--content", required=True, help="Plain text content of the note")
    p_create.add_argument("--title", default="", help="Note title (optional, max 60 chars)")
    p_create.add_argument("--board-id", dest="board_id", default="", help="Associate with a board ID")
    p_create.add_argument(
        "--gen-title",
        dest="gen_title",
        action="store_true",
        default=False,
        help="Let AI generate a title from content",
    )
    p_create.set_defaults(func=cmd_create)

    # get
    p_get = subparsers.add_parser("get", help="Get a note by ID")
    p_get.add_argument("--id", required=True, help="Note ID")
    p_get.set_defaults(func=cmd_get)

    # list
    p_list = subparsers.add_parser("list", help="List all notes in the space")
    p_list.set_defaults(func=cmd_list)

    # create-craft (document/page)
    p_craft = subparsers.add_parser(
        "create-craft",
        help="Create a craft document (type: page) — richer editor, appears as Document in board",
    )
    p_craft.add_argument("--content", required=True, help="Plain text content (markdown supported)")
    p_craft.add_argument("--title", default="", help="Document title")
    p_craft.add_argument("--board-id", dest="board_id", required=True, help="Target board ID")
    p_craft.set_defaults(func=cmd_create_craft)

    args = parser.parse_args()
    try:
        args.func(args)
    except AuthError as e:
        print(f"Auth error: {e}", file=sys.stderr)
        sys.exit(1)
    except ApiError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
