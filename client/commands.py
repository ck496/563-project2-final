"""Parse player input into command tuples."""


def parse(line: str) -> tuple[str, dict]:
    """Turn a raw input line into (command, args_dict).

    /vote <name>   -> ("vote",  {"name": "<name>"})
    /save          -> ("witch", {"action": "save"})
    /poison <name> -> ("witch", {"action": "poison", "name": "<name>"})
    /pass          -> ("witch", {"action": "pass"})
    bare text      -> ("chat",  {"text": "<text>"})
    unknown /cmd   -> ("unknown", {})
    empty line     -> ("empty", {})
    """
    stripped = line.strip()
    if not stripped:
        return ("empty", {})

    # Slash commands
    if stripped.startswith("/"):
        parts = stripped.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/vote" and arg:
            return ("vote", {"name": arg})
        if cmd == "/save":
            return ("witch", {"action": "save"})
        if cmd == "/poison" and arg:
            return ("witch", {"action": "poison", "name": arg})
        if cmd == "/pass":
            return ("witch", {"action": "pass"})

        # Missing argument or unrecognized slash command
        return ("unknown", {})

    # Bare text is chat
    return ("chat", {"text": stripped})
