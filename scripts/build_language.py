"""Normalize Foundry localization JSON without dropping or overwriting entries."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def parse_json(text):
    return json.loads(text.lstrip("\ufeff"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant)


def flatten(data):
    if not isinstance(data, dict):
        raise ValueError("The language file must contain a JSON object")
    leaves = {}

    def visit(obj, prefix=()):
        for key, value in obj.items():
            parts = tuple(key.split("."))
            if any(not part for part in parts):
                raise ValueError(f"Empty path segment in key: {key!r}")
            path = prefix + parts
            if isinstance(value, dict) and value:
                visit(value, path)
            else:
                if path in leaves:
                    raise ValueError(f"Duplicate translation path: {'.'.join(path)}")
                leaves[path] = value

    visit(data)
    return leaves


def normalize(data):
    leaves = flatten(data)
    # Detect both input orders before building any output. Arrays and empty
    # objects are leaves too, so they cannot be replaced by nested branches.
    for path in leaves:
        for length in range(1, len(path)):
            prefix = path[:length]
            if prefix in leaves:
                raise ValueError(
                    f"Leaf/object conflict: {'.'.join(prefix)} conflicts with "
                    f"{'.'.join(path)}; fix the source translation first"
                )
    result = {}
    for path, value in sorted(leaves.items()):
        current = result
        for part in path[:-1]:
            current = current.setdefault(part, {})
        current[path[-1]] = value
    if flatten(result) != leaves:
        raise ValueError("Translation paths or values changed during normalization")
    return result


def build(source, destination=None):
    data = parse_json(Path(source).read_text(encoding="utf-8-sig"))
    normalized = normalize(data)
    serialized = json.dumps(normalized, ensure_ascii=False, allow_nan=False,
                            indent=2) + "\n"
    if flatten(parse_json(serialized)) != flatten(data):
        raise ValueError("Serialized output does not match the source translations")
    if destination is not None:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(serialized)
            # Complete validation before replacing the destination, including
            # when the input and output are the same file.
            if flatten(parse_json(temporary.read_text(encoding="utf-8"))) != flatten(data):
                raise ValueError("Written output failed translation validation")
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return len(flatten(normalized))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", nargs="?", type=Path,
                        help="Omit to validate only")
    args = parser.parse_args()
    try:
        count = build(args.source, args.destination)
    except (ValueError, OSError) as error:
        print(f"Localization build failed: {error}", file=sys.stderr)
        return 1
    print(f"Validated {count} translation entries" +
          (f"; wrote {args.destination}" if args.destination else "; no files written"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
