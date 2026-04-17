#!/usr/bin/env python3
"""Doctor JDG — preflight check konfiguracji."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from jdg_ksiegowy.doctor import format_report, run_doctor


def main():
    parser = argparse.ArgumentParser(description="Doctor JDG — sprawdz konfiguracje")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit kod != 0 gdy sa bledy")
    args = parser.parse_args()

    report = run_doctor()

    if args.format == "json":
        out = {
            "ok_count": report.ok_count,
            "warnings": len(report.warnings),
            "errors": len(report.errors),
            "findings": [
                {"level": f.level, "area": f.area, "message": f.message}
                for f in report.findings
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))

    if args.fail_on_error and report.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
