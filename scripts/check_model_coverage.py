from __future__ import annotations
import csv, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("additional_research_recommended", "research_priority", "recommended_marketplaces", "recommended_query", "missing_critical_fields", "recommendation_reasons")
def main():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/report_model_coverage.py")], cwd=ROOT, capture_output=True, text=True)
    failures=[]
    if result.returncode: failures.append("report_failed")
    with (ROOT / "output/model_coverage.csv").open(encoding="utf-8", newline="") as handle: rows=list(csv.DictReader(handle))
    if rows and any(field not in rows[0] for field in REQUIRED): failures.append("missing_recommendation_columns")
    for row in rows:
        if row.get("research_priority") not in {"high","medium","low"}: failures.append("invalid_priority")
        if row.get("additional_research_recommended") == "True" and not row.get("recommendation_reasons"): failures.append("missing_reasons")
    if failures: print("FAIL\n"+"\n".join(sorted(set(failures)))); return 1
    print("Result: OK"); return 0
if __name__ == "__main__": raise SystemExit(main())
