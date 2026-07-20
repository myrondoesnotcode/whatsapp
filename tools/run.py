#!/usr/bin/env python3
"""Analyse WhatsApp chat exports and produce an HTML dashboard.

Usage:
    python3 run.py                 # process every export in inbox/
    python3 run.py path/to/chat.txt
    python3 run.py --open          # open each report when it's done

Everything runs locally. No network calls, no API keys, no dependencies
beyond the Python standard library.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import traceback
from pathlib import Path

from analyzer import extract, report, stats
from analyzer.parser import parse
from analyzer.tools_dict import COMPILED

ROOT = Path(__file__).parent
INBOX = ROOT / "inbox"
OUTPUT = ROOT / "output"


def analyse(path: Path, *, open_when_done: bool = False) -> Path:
    print(f"\n  Reading {path.name} …")
    chat = parse(path)

    people_count = len(chat.people_messages)
    print(f"   parsed {people_count:,} messages from {len(chat.participants)} people")
    if chat.warnings:
        for warning in chat.warnings:
            print(f"   note: {warning}")

    print("   extracting links, tools and signals …")
    links = extract.extract_links(chat)
    tools = extract.extract_tools(chat)
    discovered = extract.discover_unknown_tools(chat, set(COMPILED))
    signals = extract.extract_signals(chat)
    questions = extract.extract_questions(chat)

    print("   computing statistics …")
    overview = stats.build_overview(chat, len(links))
    people = stats.build_person_stats(chat)

    OUTPUT.mkdir(exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in path.stem)
    out_path = OUTPUT / f"{safe_name.strip() or 'chat'}.html"

    print("   building dashboard …")
    report.build(
        chat,
        overview=overview,
        people=people,
        links=links,
        tools=tools,
        discovered=discovered,
        signals=signals,
        questions=questions,
        out_path=out_path,
    )

    signal_total = sum(len(v) for v in signals.values())
    print(
        f"   found {len(links):,} links · {len(tools)} known tools · "
        f"{signal_total:,} signal matches · {len(questions):,} questions"
    )
    print(f"   → {out_path}")

    if open_when_done and sys.platform == "darwin":
        subprocess.run(["open", str(out_path)], check=False)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", type=Path, help="export files (.txt or .zip)")
    ap.add_argument("--open", action="store_true", help="open reports when finished")
    args = ap.parse_args()

    if args.files:
        targets = args.files
    else:
        INBOX.mkdir(exist_ok=True)
        targets = sorted(
            p
            for p in INBOX.iterdir()
            if p.suffix.lower() in {".txt", ".zip"} and not p.name.startswith(".")
        )

    if not targets:
        print(
            "No exports found.\n\n"
            f"Drop a WhatsApp export (.txt or .zip) into:\n  {INBOX}\n\n"
            "In WhatsApp: open the chat → group name → Export Chat → "
            "Without Media → save the file to your Mac."
        )
        return 1

    print(f"Found {len(targets)} export(s) to analyse.")
    failures = 0
    for path in targets:
        if not path.exists():
            print(f"\n  ✗ {path} does not exist")
            failures += 1
            continue
        try:
            analyse(path, open_when_done=args.open)
        except Exception as exc:  # noqa: BLE001 — one bad file shouldn't stop the rest
            failures += 1
            print(f"\n  ✗ {path.name}: {exc}")
            if "--debug" in sys.argv:
                traceback.print_exc()

    done = len(targets) - failures
    print(f"\nDone. {done} report(s) written to {OUTPUT}")
    return 1 if failures and not done else 0


if __name__ == "__main__":
    raise SystemExit(main())
