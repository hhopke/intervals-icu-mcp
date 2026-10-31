"""Smoke eval for first-tool-call routing accuracy.

Hits the Anthropic API with the MCP server's tool definitions and a set of
prompts, then records which tool the model picked first. Pure routing test —
never sends a tool_result back, so no MCP tool is ever executed. The
intervals.icu API is never touched.

Usage:
    ANTHROPIC_API_KEY=... uv run python scripts/smoke_eval.py
    ANTHROPIC_API_KEY=... uv run python scripts/smoke_eval.py --output results.json
    uv run python scripts/smoke_eval.py --cases tests/smoke_eval.json --model claude-haiku-4-5-20251001

Costs ~$0.07 per full run on Haiku 4.5. NOT part of `make test`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import anthropic
from fastmcp import Client

from intervals_icu_mcp.server import mcp

# Hard guard: this harness must never execute any tool. We accept tool_use blocks
# from the model and inspect them, but we never construct or send a tool_result.
# Changing this constant requires a deliberate code change, not a flag.
DRY_RUN = True

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_CASES_PATH = Path(__file__).parent.parent / "tests" / "smoke_eval.json"


@dataclass
class CaseResult:
    id: str
    prompt: str
    expected: str
    got: str | None
    passed: bool
    bucket: str
    notes: str


async def get_anthropic_tool_defs() -> list[dict[str, Any]]:
    """Return MCP tool defs converted to Anthropic API tool-use format.

    Differences from the MCP protocol's Tool type:
    - Field rename: `inputSchema` -> `input_schema`.
    - Drop fields Anthropic doesn't consume: annotations, meta, icons, etc.
    """
    async with Client(mcp) as client:
        tools = await client.list_tools()
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.input_schema,
        }
        for t in tools
    ]


def extract_first_tool_use(response: anthropic.types.Message) -> str | None:
    """Return the name of the first tool_use block, or None if model didn't pick one."""
    for block in response.content:
        if block.type == "tool_use":
            return block.name
    return None


def run_case(
    client: anthropic.Anthropic,
    case: dict[str, Any],
    tools: list[dict[str, Any]],
    model: str,
) -> CaseResult:
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=tools,  # type: ignore[arg-type]
        messages=[{"role": "user", "content": case["prompt"]}],
    )
    got = extract_first_tool_use(response)
    expected = case["expected_tool"]
    return CaseResult(
        id=case["id"],
        prompt=case["prompt"],
        expected=expected,
        got=got,
        passed=(got == expected),
        bucket=case.get("bucket", ""),
        notes=case.get("notes", ""),
    )


def print_summary(results: list[CaseResult]) -> None:
    width_id = max(len(r.id) for r in results) + 2
    width_exp = max(len(r.expected) for r in results) + 2
    print(f"{'STATUS':<6} {'CASE':<{width_id}} {'EXPECTED':<{width_exp}} GOT")
    print("-" * (10 + width_id + width_exp + 35))
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        got = r.got or "(none)"
        print(f"{status:<6} {r.id:<{width_id}} {r.expected:<{width_exp}} {got}")
    print()
    passed = sum(1 for r in results if r.passed)
    print(f"{passed}/{len(results)} passed")
    failed_ids = [r.id for r in results if not r.passed]
    if failed_ids:
        print(f"Failed cases: {', '.join(failed_ids)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help=f"Path to eval cases JSON (default: {DEFAULT_CASES_PATH.relative_to(Path.cwd()) if DEFAULT_CASES_PATH.is_relative_to(Path.cwd()) else DEFAULT_CASES_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to save results JSON (for `smoke_eval_diff.py`)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model ID (default: {DEFAULT_MODEL})",
    )
    args = parser.parse_args()

    assert DRY_RUN, "DRY_RUN must remain True; this harness never executes tools"

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "Error: ANTHROPIC_API_KEY is required. Get one at https://console.anthropic.com.",
            file=sys.stderr,
        )
        return 2

    if not args.cases.exists():
        print(f"Error: cases file not found: {args.cases}", file=sys.stderr)
        return 2

    cases = json.loads(args.cases.read_text())
    print("Loading MCP tool defs (in-process)...")
    tools = asyncio.run(get_anthropic_tool_defs())
    print(f"Loaded {len(tools)} tools. Running {len(cases)} cases against {args.model}.")
    print()

    client = anthropic.Anthropic()
    results: list[CaseResult] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']}...", end="", flush=True)
        try:
            result = run_case(client, case, tools, args.model)
        except anthropic.APIError as e:
            print(f" ERROR: {e}")
            result = CaseResult(
                id=case["id"],
                prompt=case["prompt"],
                expected=case["expected_tool"],
                got=None,
                passed=False,
                bucket=case.get("bucket", ""),
                notes=f"API error: {e}",
            )
        else:
            print(" PASS" if result.passed else f" FAIL (got {result.got})")
        results.append(result)

    print()
    print_summary(results)

    if args.output:
        args.output.write_text(json.dumps([asdict(r) for r in results], indent=2))
        print(f"\nResults saved to {args.output}")

    failed = sum(1 for r in results if not r.passed)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
