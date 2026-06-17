"""Ingest stage: parse delimited text feeds into typed row dicts.

Lines are comma-separated with optional double-quoted fields. The entry
point is ``parse_records(lines, schema)``, which parses a batch of lines
against a schema of ``(name, kind)`` pairs and skips lines that do not
conform. Supported kinds: ``"str"``, ``"int"``, ``"float"``, ``"flag"``.
"""

_TRUE_FLAGS = {"yes", "true", "y", "1"}
_FALSE_FLAGS = {"no", "false", "n", "0"}


def split_fields(line):
    """Split one raw line into field strings, honoring double quotes."""
    fields = []
    buf = []
    in_quotes = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_quotes:
            if ch == '"':
                in_quotes = False
            else:
                buf.append(ch)
        elif ch == '"':
            in_quotes = True
        elif ch == ",":
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    fields.append("".join(buf))
    return fields


def coerce(text, kind):
    """Coerce one raw field to ``kind``; an empty field becomes None."""
    text = text.strip()
    if text == "":
        return None
    if kind == "str":
        return text
    if kind == "int":
        value = float(text)
        if value != int(value):
            raise ValueError(f"not an integer: {text!r}")
        return int(value)
    if kind == "float":
        return float(text)
    if kind == "flag":
        low = text.lower()
        if low in _TRUE_FLAGS:
            return True
        if low in _FALSE_FLAGS:
            return False
        raise ValueError(f"not a flag: {text!r}")
    raise ValueError(f"unknown kind: {kind!r}")


def parse_record(line, schema):
    """Parse one line against ``schema``; raise ValueError if it does not conform."""
    parts = split_fields(line)
    if len(parts) != len(schema):
        raise ValueError(f"expected {len(schema)} fields, got {len(parts)}")
    return {name: coerce(part, kind) for (name, kind), part in zip(schema, parts)}


def parse_records(lines, schema):
    """Parse a batch of lines, skipping blanks, comments and bad records."""
    rows = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            rows.append(parse_record(line, schema))
        except ValueError:
            continue
    return rows


def column(rows, name):
    """Extract one field from every row, in input order."""
    return [row.get(name) for row in rows]
