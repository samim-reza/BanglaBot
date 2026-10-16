"""CLI: run scenarios concurrently, print a summary, write the report."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.scenarios")
    parser.add_argument("--only", default="", help="comma-separated id prefixes")
    parser.add_argument("--failed", default="", help="results.json of an earlier run: re-run only its failures")
    parser.add_argument("--repeat", type=int, default=1, help="run each scenario N times (catches flaky behaviour)")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument(
        "--agent-llm", default="openai:gpt-5.4-mini,groq:openai/gpt-oss-120b",
        help="LLM_CHAIN for the agent under test, like production: OpenAI first, a fallback behind it ('' = .env chain)",
    )
    parser.add_argument("--out", default="", help="report folder (default .scenario-reports/<timestamp>)")
    parser.add_argument("--list", action="store_true")
    return parser.parse_args()


async def _main(args: argparse.Namespace) -> int:
    from app.flows.timefmt import business_tz
    from scripts.scenarios.cases import all_scenarios
    from scripts.scenarios.dates import pinned_now
    from scripts.scenarios.openai_chat import OpenAIChat
    from scripts.scenarios.report import write
    from scripts.scenarios.runner import run_scenario

    now = pinned_now(business_tz("America/New_York"))
    scenarios = all_scenarios(now)
    if args.failed:
        failed = {row["id"] for row in json.loads(Path(args.failed).read_text()) if not row["passed"]}
        scenarios = [s for s in scenarios if s.id in failed]
    if args.only:
        prefixes = tuple(p.strip() for p in args.only.split(",") if p.strip())
        scenarios = [s for s in scenarios if s.id.startswith(prefixes)]
    if args.list:
        for s in scenarios:
            print(f"{s.id:40s} {s.title}")
        print(f"{len(scenarios)} scenarios")
        return 0
    runs = [s for s in scenarios for _ in range(max(1, args.repeat))]
    print(f"Running {len(runs)} conversations (business time pinned to {now:%a %Y-%m-%d %H:%M %Z}) ...", flush=True)
    chat = OpenAIChat()
    gate = asyncio.Semaphore(max(1, args.concurrency))
    started = time.monotonic()

    async def one(scenario):  # noqa: ANN001, ANN202
        async with gate:
            result = await run_scenario(scenario, chat, now=now, use_judge=not args.no_judge)
            mark = "PASS" if result.passed else "FAIL"
            why = result.error or "; ".join(result.problems) or (result.verdict.get("summary") if not result.passed else "")
            print(f"  {mark} {scenario.id} ({result.seconds}s){' — ' + str(why)[:160] if why else ''}", flush=True)
            return result

    results = await asyncio.gather(*(one(s) for s in runs))
    await chat.aclose()
    out = Path(args.out) if args.out else Path(".scenario-reports") / time.strftime("%Y%m%d-%H%M%S")
    json_path, md_path = write(results, out)
    passed = sum(1 for r in results if r.passed)
    print(f"\n{passed}/{len(results)} passed in {int(time.monotonic() - started)}s · caller+judge tokens {chat.prompt_tokens}+{chat.completion_tokens}")
    print(f"Report: {md_path}\nData:   {json_path}")
    return 0 if passed == len(results) else 1


def main() -> None:
    args = _parse()
    if args.agent_llm:
        # Must be set before the app's settings are first read.
        os.environ["LLM_CHAIN"] = args.agent_llm
        os.environ["LLM_ALLOW_PAID"] = "true"
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
