"""Chạy eval: python -m evals.run [--suite all|generation|...] [--quick]

Ghi report JSON vào evals/reports/latest.json, in bảng markdown (và ghi vào
$GITHUB_STEP_SUMMARY khi chạy trên GitHub Actions). Exit code 1 nếu có chỉ số
dưới ngưỡng trong evals/thresholds.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from evals.suites import SUITES, SuiteResult
from evals import llm as ev
from app.services.llm_service import llm_service

ROOT = Path(__file__).parent
THRESHOLDS = json.loads((ROOT / "thresholds.json").read_text(encoding="utf-8"))

QUICK = {"solver_baseline": {"limit": 15}, "generation": {"samples_per_part": 1},
         "explain": {"limit": 8}, "chat": {"limit": 6}}
FULL = {"solver_baseline": {}, "generation": {"samples_per_part": 3}, "explain": {}, "chat": {}}


def check(result: SuiteResult) -> list[dict]:
    """-> danh sách chỉ số kèm ngưỡng và pass/fail."""
    rows = []
    for metric, rule in THRESHOLDS.get(result.name, {}).items():
        value = result.metrics.get(metric)
        if value is None:
            continue
        ok = (value >= rule["min"]) if "min" in rule else (value <= rule["max"])
        bound = f">= {rule['min']}" if "min" in rule else f"<= {rule['max']}"
        rows.append({"metric": metric, "value": value, "threshold": bound, "passed": ok})
    return rows


def to_markdown(report: dict) -> str:
    lines = [
        "## ViEng eval",
        f"Model: `{report['models']['app']}` · solver: `{report['models']['solver']}` · "
        f"judge: `{report['models']['judge']}` · mode: {report['mode']}",
        "",
        "| Suite | Metric | Value | Threshold | |",
        "|---|---|---|---|---|",
    ]
    for s in report["suites"]:
        for r in s["checks"]:
            lines.append(f"| {s['name']} | {r['metric']} | {r['value']} | {r['threshold']} | "
                         f"{'✅' if r['passed'] else '❌'} |")
        if s.get("error"):
            lines.append(f"| {s['name']} | error | {s['error']} | | ❌ |")
    lines.append("")
    lines.append(f"**{'PASS' if report['passed'] else 'FAIL'}** · {report['elapsed_s']}s")
    return "\n".join(lines)


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="all", help="all hoặc tên suite, phân tách bởi dấu phẩy")
    ap.add_argument("--quick", action="store_true", help="ít mẫu hơn (cho PR)")
    ap.add_argument("--out", default=str(ROOT / "reports" / "latest.json"))
    args = ap.parse_args(argv)

    names = list(SUITES) if args.suite == "all" else [s.strip() for s in args.suite.split(",")]
    params = QUICK if args.quick else FULL

    t0 = time.perf_counter()
    suites = []
    for name in names:
        try:
            res = await SUITES[name](**params.get(name, {}))
            checks = check(res)
            suites.append({"name": name, "metrics": res.metrics, "checks": checks,
                           "failures": res.failures[:50]})
        except Exception as e:  # noqa: BLE001 - suite lỗi = fail, vẫn chạy suite khác
            suites.append({"name": name, "metrics": {}, "checks": [], "failures": [],
                           "error": f"{type(e).__name__}: {e}"})

    passed = all(c["passed"] for s in suites for c in s["checks"]) and not any(s.get("error") for s in suites)
    report = {
        "mode": "quick" if args.quick else "full",
        "models": {"app": llm_service.model, "solver": ev.solver_model(), "judge": ev.judge_model()},
        "suites": suites,
        "passed": passed,
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = to_markdown(report)
    print(md)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
