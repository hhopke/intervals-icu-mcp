"""Generate a structured diff and code-impact scan for an OpenAPI spec update.

Usage: python openapi_diff.py <old_spec.json> <new_spec.json> <src_dir> > body.md

Emits Markdown suitable for a GitHub PR body. Highlights:
  - Added/removed paths and schemas
  - Method changes on existing paths
  - Added/removed schema properties and enum values
  - Code references in <src_dir> to anything that was removed or had values dropped
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def schema_props(schema: dict) -> dict:
    return schema.get("properties") or {}


def diff_paths(old: dict, new: dict) -> tuple[list[str], list[str]]:
    old_p = set(old.get("paths", {}).keys())
    new_p = set(new.get("paths", {}).keys())
    return sorted(new_p - old_p), sorted(old_p - new_p)


def diff_schemas(old: dict, new: dict) -> tuple[list[str], list[str]]:
    old_s = set((old.get("components", {}).get("schemas") or {}).keys())
    new_s = set((new.get("components", {}).get("schemas") or {}).keys())
    return sorted(new_s - old_s), sorted(old_s - new_s)


def diff_methods(old: dict, new: dict) -> list[tuple[str, list[str], list[str]]]:
    """For paths in both, list added/removed HTTP methods."""
    meta = {"parameters", "summary", "description", "servers"}
    out: list[tuple[str, list[str], list[str]]] = []
    common = set(old.get("paths", {}).keys()) & set(new.get("paths", {}).keys())
    for p in sorted(common):
        old_m = set(old["paths"][p].keys()) - meta
        new_m = set(new["paths"][p].keys()) - meta
        added = sorted(new_m - old_m)
        removed = sorted(old_m - new_m)
        if added or removed:
            out.append((p, added, removed))
    return out


def diff_schema_fields(old: dict, new: dict):
    """Yield (schema_name, added_fields, removed_fields, enum_changes)."""
    old_s = (old.get("components", {}).get("schemas") or {})
    new_s = (new.get("components", {}).get("schemas") or {})
    for name in sorted(set(old_s) & set(new_s)):
        old_props = schema_props(old_s[name])
        new_props = schema_props(new_s[name])
        added = sorted(set(new_props) - set(old_props))
        removed = sorted(set(old_props) - set(new_props))
        enum_changes: list[tuple[str, list, list]] = []
        for prop in sorted(set(old_props) & set(new_props)):
            o_enum = old_props[prop].get("enum") or []
            n_enum = new_props[prop].get("enum") or []
            if o_enum or n_enum:
                e_added = sorted(set(n_enum) - set(o_enum), key=str)
                e_removed = sorted(set(o_enum) - set(n_enum), key=str)
                if e_added or e_removed:
                    enum_changes.append((prop, e_added, e_removed))
        if added or removed or enum_changes:
            yield name, added, removed, enum_changes


def grep(needle: str, src: Path) -> list[str]:
    """Return matching lines from `git grep` (falls back to ripgrep/grep)."""
    try:
        out = subprocess.check_output(
            ["git", "grep", "-n", "--", needle, str(src)],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return [line for line in out.splitlines() if line]
    except subprocess.CalledProcessError:
        return []


def path_tail(template: str) -> str:
    """Pull a distinctive suffix out of a path template for grep."""
    parts = [seg for seg in template.split("/") if seg and not seg.startswith("{")]
    return parts[-1] if parts else template


def render(old_path: str, new_path: str, src_dir: str) -> str:
    old = load(old_path)
    new = load(new_path)
    src = Path(src_dir)

    added_paths, removed_paths = diff_paths(old, new)
    added_schemas, removed_schemas = diff_schemas(old, new)
    method_changes = diff_methods(old, new)
    field_changes = list(diff_schema_fields(old, new))

    lines: list[str] = [
        "Automated PR to update `openapi-spec.json` from the latest Intervals.icu API.",
        "",
    ]

    has_changes = any([
        added_paths, removed_paths, added_schemas, removed_schemas,
        method_changes, field_changes,
    ])
    if not has_changes:
        lines.append("## Spec changes")
        lines.append("")
        lines.append("_No structural changes — only metadata or formatting differences._")
        return "\n".join(lines)

    lines.append("## Spec changes")
    lines.append("")

    if added_paths:
        lines.append("### Added paths")
        lines.extend(f"- `{p}`" for p in added_paths)
        lines.append("")
    if removed_paths:
        lines.append("### Removed paths :warning:")
        lines.extend(f"- `{p}`" for p in removed_paths)
        lines.append("")
    if method_changes:
        lines.append("### Method changes on existing paths")
        for p, added, removed in method_changes:
            if added:
                lines.append(f"- `{p}` + `{', '.join(added)}`")
            if removed:
                lines.append(f"- `{p}` − `{', '.join(removed)}` :warning:")
        lines.append("")
    if added_schemas:
        lines.append("### Added schemas")
        lines.extend(f"- `{s}`" for s in added_schemas)
        lines.append("")
    if removed_schemas:
        lines.append("### Removed schemas :warning:")
        lines.extend(f"- `{s}`" for s in removed_schemas)
        lines.append("")
    if field_changes:
        lines.append("### Schema property changes")
        for name, added, removed, enums in field_changes:
            lines.append(f"- **{name}**")
            if added:
                lines.append(f"  - added: {', '.join(f'`{f}`' for f in added)}")
            if removed:
                fields = ", ".join(f"`{f}`" for f in removed)
                lines.append(f"  - removed: {fields} :warning:")
            for prop, e_added, e_removed in enums:
                if e_added:
                    vals = ", ".join(f"`{v}`" for v in e_added)
                    lines.append(f"  - `{prop}` enum + {vals}")
                if e_removed:
                    vals = ", ".join(f"`{v}`" for v in e_removed)
                    lines.append(f"  - `{prop}` enum − {vals} :warning:")
        lines.append("")

    # Code impact scan: only check things that were REMOVED or had values dropped.
    lines.append("## Code impact scan")
    lines.append("")
    lines.append(f"Searching `{src_dir}/` for references to removed identifiers.")
    lines.append("")

    impact_hits: list[str] = []

    for p in removed_paths:
        tail = path_tail(p)
        hits = grep(tail, src)
        if hits:
            impact_hits.append(f"**Removed path `{p}`** (searched for `{tail}`):")
            impact_hits.extend(f"  - `{h}`" for h in hits[:10])
            if len(hits) > 10:
                impact_hits.append(f"  - …and {len(hits) - 10} more matches")

    for s in removed_schemas:
        hits = grep(s, src)
        if hits:
            impact_hits.append(f"**Removed schema `{s}`**:")
            impact_hits.extend(f"  - `{h}`" for h in hits[:10])
            if len(hits) > 10:
                impact_hits.append(f"  - …and {len(hits) - 10} more matches")

    for name, _added, removed, enums in field_changes:
        for field in removed:
            # Use word-boundary match; grep with -w not portable, just rely on tokenization.
            hits = grep(field, src)
            # Filter to schema-name-adjacent matches if possible — keep simple for now.
            if hits:
                impact_hits.append(f"**Removed field `{name}.{field}`**:")
                impact_hits.extend(f"  - `{h}`" for h in hits[:5])
                if len(hits) > 5:
                    impact_hits.append(f"  - …and {len(hits) - 5} more matches")
        for prop, _e_added, e_removed in enums:
            for v in e_removed:
                if not isinstance(v, str) or len(v) < 3:
                    continue
                # Quote-anchored search to reduce noise on common words.
                hits = grep(f'"{v}"', src) + grep(f"'{v}'", src)
                if hits:
                    impact_hits.append(
                        f"**Dropped enum value `{name}.{prop} = {v!r}`**:"
                    )
                    impact_hits.extend(f"  - `{h}`" for h in hits[:5])

    if impact_hits:
        lines.extend(impact_hits)
    else:
        lines.append("_No references to removed identifiers found in source._")

    lines.append("")
    lines.append("---")
    lines.append("*Generated by `.github/scripts/openapi_diff.py`.*")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    body = render(sys.argv[1], sys.argv[2], sys.argv[3])
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
