"""Run one check from the command line — same pipeline as the bot, no Telegram needed.

    python check.py example.com
    python check.py https://example.com --lang ru --json result.json --shots shots/
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import html
import json
import logging
import re
import sys
from pathlib import Path

from aichecker import report
from aichecker.config import load_settings
from aichecker.pipeline import Checker, CheckError
from aichecker.urlguard import UrlError


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def run(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.allow_private:
        settings = dataclasses.replace(settings, allow_private_urls=True)
    logging.basicConfig(level=logging.WARNING if not args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    checker = Checker(settings)
    await checker.start()

    async def progress(device: str, stage: str) -> None:
        print(f"  {report.ICONS[device]} {device}: {stage}", file=sys.stderr)

    try:
        result = await checker.check(args.url, args.lang, progress)
    except UrlError as exc:
        print(f"Bad URL ({exc.code}): {exc}", file=sys.stderr)
        return 2
    except CheckError as exc:
        print(plain(report.render_error(report.host_of(args.url), exc.code, exc.detail, args.lang)),
              file=sys.stderr)
        return 1
    finally:
        await checker.close()

    print(plain(report.render_report(result, args.lang, settings)))
    print("\n" + "─" * 60 + "\n")
    print(plain(report.render_details(result, args.lang, settings)))
    if args.json:
        Path(args.json).write_text(json.dumps(report.to_record(result), ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"\nJSON written to {args.json}", file=sys.stderr)
    if args.shots:
        folder = Path(args.shots)
        folder.mkdir(parents=True, exist_ok=True)
        for device, run_ in result.runs.items():
            for screen in run_.capture.screens if run_.capture else []:
                (folder / f"{device}_{screen.index:02d}_{screen.zone}.jpg").write_bytes(screen.jpeg)
        print(f"Screenshots saved to {folder}/", file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Check how AI-generated a website looks.")
    parser.add_argument("url")
    parser.add_argument("--lang", choices=("en", "ru"), default="en")
    parser.add_argument("--json", metavar="FILE", help="write the full result record as JSON")
    parser.add_argument("--shots", metavar="DIR", help="save the analyzed screenshots")
    parser.add_argument("--allow-private", action="store_true", help="allow localhost / private IPs")
    parser.add_argument("-v", "--verbose", action="store_true")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
