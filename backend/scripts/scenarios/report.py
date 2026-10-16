"""Write a scenario run as JSON (everything) and Markdown (failures first, with transcripts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.scenarios.model import RunResult


def _row(result: RunResult) -> dict[str, Any]:
    return {
        "id": result.scenario.id,
        "vertical": result.scenario.vertical,
        "title": result.scenario.title,
        "passed": result.passed,
        "error": result.error,
        "problems": result.problems,
        "verdict": result.verdict,
        "seconds": result.seconds,
        "stats": result.stats,
        "state": {k: result.state.get(k) for k in ("stage", "outcome", "ended")},
        "commits": [{"outcome": c["action"].outcome, "status": str(c["action"].status), "fields": c["action"].fields} for c in result.commits],
        "transcript": result.transcript(),
    }


def write(results: list[RunResult], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [_row(r) for r in results]
    json_path = out_dir / "results.json"
    json_path.write_text(json.dumps(rows, indent=1, default=str, ensure_ascii=False))
    passed = sum(1 for r in results if r.passed)
    lines = [f"# Scenario run: {passed}/{len(results)} passed", ""]
    lines.append("| Scenario | Result | Why |")
    lines.append("|---|---|---|")
    for row in sorted(rows, key=lambda r: (r["passed"], r["vertical"], r["id"])):
        why = row["error"] or "; ".join(row["problems"]) or "; ".join(
            str(i.get("detail", i)) if isinstance(i, dict) else str(i) for i in (row["verdict"].get("issues") or []) if not isinstance(i, dict) or i.get("severity") == "major"
        )
        lines.append(f"| `{row['id']}` | {'PASS' if row['passed'] else '**FAIL**'} | {why[:300].replace('|', '/')} |")
    for row in rows:
        if row["passed"]:
            continue
        lines += ["", f"## {row['id']} — {row['title']}", "", "```", row["transcript"], "```", ""]
        lines.append(f"Saved: `{json.dumps(row['commits'], default=str, ensure_ascii=False)[:1500]}`")
        lines.append(f"Final: `{row['state']}`")
        if row["verdict"]:
            lines.append(f"Judge: {json.dumps(row['verdict'], ensure_ascii=False)[:2000]}")
    md_path = out_dir / "report.md"
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path
