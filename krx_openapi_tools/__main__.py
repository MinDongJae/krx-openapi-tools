import argparse
import json
import os
import sys
from pathlib import Path

from .core import Client, KRXError, contract, normalize, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect KRX contracts and validate daily equity responses")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("catalog", "validate", "fetch"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--market", required=True, choices=["kospi", "kosdaq", "konex"])
        if name != "catalog":
            cmd.add_argument("--date")
        if name == "validate":
            cmd.add_argument("file", type=Path)
            cmd.add_argument("--normalized", action="store_true")
        if name == "fetch":
            cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            result = contract(args.market)
        elif args.command == "validate":
            payload = json.loads(args.file.read_text(encoding="utf-8-sig"))
            report = validate(payload, args.market, expected_date=args.date)
            result = report.to_dict()
            if report.valid and args.normalized:
                result["normalized"] = normalize(payload, args.market, expected_date=args.date)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if report.valid else 1
        else:
            if not args.date:
                parser.error("fetch requires --date")
            if args.output.exists():
                raise ValueError("Output already exists; choose a new path")
            result = Client(os.environ.get("KRX_AUTH_KEY", "")).fetch(args.market, args.date)
            # Exclusive creation also protects against a file appearing during the request.
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
            print(json.dumps({"saved": str(args.output), "validation": result["validation"]}, ensure_ascii=False))
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KRXError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
