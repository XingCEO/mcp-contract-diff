"""Catch tool-contract breaks before an agent discovers them at runtime."""


def pointer(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def analyze(data):
    findings = []

    def emit(tool, path, kind, detail):
        findings.append(dict(tool=tool, path=path, severity=kind, detail=detail))

    def catalog(value):
        result = {}
        for tool in value["tools"]:
            name = tool["name"]
            if name in result:
                raise ValueError("duplicate tool: " + name)
            result[name] = tool
        return result

    def compare(tool, old, new, path, output=False):
        if old == new:
            return
        if not isinstance(old, dict) or not isinstance(new, dict):
            emit(tool, path, "review", "Boolean or non-object schema changed")
            return
        ot, nt = old.get("type"), new.get("type")
        if ot != nt:
            emit(tool, path + "/type", "review", f"Type changed: {ot!r} -> {nt!r}")
        ore, nre = set(old.get("required", [])), set(new.get("required", []))
        changed = ore - nre if output else nre - ore
        for field in sorted(changed):
            emit(
                tool,
                path + "/required",
                "breaking",
                ("Output no longer guarantees " if output else "Input now requires ")
                + field,
            )
        if "enum" in old or "enum" in new:
            old_enum, new_enum = old.get("enum"), new.get("enum")
            import json

            canon = lambda items: {json.dumps(v, sort_keys=True) for v in items}
            incompatible = (
                (
                    old_enum is not None
                    and (new_enum is None or not canon(new_enum) <= canon(old_enum))
                )
                if output
                else (
                    new_enum is not None
                    and (old_enum is None or not canon(old_enum) <= canon(new_enum))
                )
            )
            if incompatible:
                emit(
                    tool,
                    path + "/enum",
                    "breaking",
                    "Output enum expanded"
                    if output
                    else "Accepted input enum narrowed",
                )
        if (
            not output
            and old.get("additionalProperties", True) is not False
            and new.get("additionalProperties", True) is False
        ):
            emit(
                tool,
                path + "/additionalProperties",
                "breaking",
                "Extra input fields are now rejected",
            )
        op, np = old.get("properties", {}), new.get("properties", {})
        for field in sorted(op.keys() - np.keys()):
            emit(
                tool,
                path + "/properties/" + pointer(field),
                "review",
                "Property removed; inspect additionalProperties and consumer expectations",
            )
        for field in sorted(op.keys() & np.keys()):
            compare(
                tool,
                op[field],
                np[field],
                path + "/properties/" + pointer(field),
                output,
            )
        if "items" in old or "items" in new:
            compare(
                tool,
                old.get("items", {}),
                new.get("items", {}),
                path + "/items",
                output,
            )
        handled = {
            "type",
            "required",
            "enum",
            "properties",
            "items",
            "additionalProperties",
            "description",
            "title",
            "examples",
            "$schema",
            "default",
        }
        for key in sorted((old.keys() | new.keys()) - handled):
            if old.get(key) != new.get(key):
                emit(
                    tool,
                    path + "/" + pointer(key),
                    "review",
                    "Constraint changed; compatibility requires review",
                )
        if output and old.get("additionalProperties") != new.get(
            "additionalProperties"
        ):
            emit(
                tool,
                path + "/additionalProperties",
                "review",
                "Output object openness changed",
            )
        if (
            isinstance(new.get("additionalProperties"), dict)
            and old.get("additionalProperties") != new["additionalProperties"]
        ):
            emit(
                tool,
                path + "/additionalProperties",
                "review",
                "Additional-property schema changed",
            )

    before, after = catalog(data["before"]), catalog(data["after"])
    for name in sorted(before):
        if name not in after:
            emit(name, "", "breaking", "Tool removed")
            continue
        compare(
            name,
            before[name].get("inputSchema", {}),
            after[name].get("inputSchema", {}),
            "/inputSchema",
        )
        if "outputSchema" in before[name] or "outputSchema" in after[name]:
            compare(
                name,
                before[name].get("outputSchema", {}),
                after[name].get("outputSchema", {}),
                "/outputSchema",
                True,
            )
    return {
        "breaking": sum(f["severity"] == "breaking" for f in findings),
        "findings": findings,
        "added_tools": sorted(after.keys() - before.keys()),
    }


def main():
    """Analyze a JSON envelope or explicitly selected native files."""
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON input path, or - for stdin")
    parser.add_argument("--before", help="Read before directly from a local file")
    parser.add_argument("--after", help="Read after directly from a local file")

    args = parser.parse_args()
    native = bool(args.before or args.after)
    if native and (args.input or not (args.before and args.after)):
        parser.error("Supply all native file flags, without a positional JSON input")
    if not native and not args.input:
        parser.error("Supply a JSON input or native file flags")
    try:
        if native:
            data = {
                "before": json.loads(Path(args.before).read_text()),
                "after": json.loads(Path(args.after).read_text()),
            }
        else:
            raw = (
                sys.stdin.read()
                if args.input == "-"
                else Path(args.input).read_text(encoding="utf-8")
            )
            data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        result = analyze(data)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        print(f"Invalid input: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
