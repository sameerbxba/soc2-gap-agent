"""Command line entry point."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

# Without this, piping output into head raises BrokenPipeError and prints a
# traceback that looks like a failure. Found by running `agent audit | head`.
if hasattr(signal, "SIGPIPE"):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

import yaml

from .audit import AuditLog
from .guardrails import RunBudget
from .loop import AgentRun
from .providers import LiveProvider, ProviderError, ReplayProvider
from .tools import rollback_run

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "data" / "soc2_northwind_2026.md"
DEFAULT_REQS = ROOT / "data" / "requirements.yaml"
DEFAULT_REPLAY = ROOT / "data" / "replay" / "session_default.json"
DEFAULT_OUT = ROOT / "out"

VERDICT_LABEL = {
    "met": "met",
    "partially_met": "PARTIAL",
    "not_met": "NOT MET",
    "not_covered": "NOT COVERED",
    "user_entity_control": "OUR CONTROL",
}


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def print_report(result: dict) -> None:
    print("\n" + "=" * 74)
    print(f"  gap register  ({len(result['findings'])} findings)")
    print("=" * 74)
    for finding in result["findings"]:
        label = VERDICT_LABEL.get(finding["verdict"], finding["verdict"])
        print(f"\n  {finding['requirement_id']}  {finding['requirement_title']}")
        print(f"  verdict: {label}   source: p.{finding['page']}")
        for line in _wrap(finding["rationale"], 68):
            print(f"    {line}")
        quote = finding["citation"]
        if len(quote) > 180:
            quote = quote[:180] + " ..."
        for line in _wrap(f'"{quote}"', 66):
            print(f"      {line}")

    if result.get("summary"):
        print("\n" + "-" * 74)
        print("  reviewer summary")
        print("-" * 74)
        for line in _wrap(result["summary"], 70):
            print(f"  {line}")

    print("\n" + "-" * 74)
    print(f"  run id:    {result['run_id']}")
    print(f"  complete:  {result['complete']}")
    if result.get("declined"):
        print(f"  declined:  {', '.join(result['declined'])}")
    if result.get("stopped_by"):
        print(f"  stopped:   {result['stopped_by']}")
    print(f"  register:  {result['register']}")
    print(f"  audit log: {result['audit_log']}")
    u = result["usage"]
    print(
        f"  usage:     {u['iterations']} iterations, "
        f"{u['input_tokens'] + u['output_tokens']} tokens, "
        f"{u['elapsed_seconds']}s"
    )
    print(f"\n  roll back with:  python -m agent.cli rollback {result['run_id']}\n")


def _wrap(text: str, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Review a vendor SOC 2 report against a control standard.",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="run the review")
    run.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    run.add_argument("--requirements", type=Path, default=DEFAULT_REQS)
    run.add_argument("--out", type=Path, default=DEFAULT_OUT)
    run.add_argument(
        "--replay",
        nargs="?",
        const=str(DEFAULT_REPLAY),
        default=None,
        help="run from a recorded session instead of calling the API",
    )
    run.add_argument("--model", default="claude-sonnet-4-5")
    run.add_argument(
        "--record",
        type=Path,
        default=None,
        help="save this live run's turns to a file for later replay",
    )
    run.add_argument(
        "--approve-all",
        action="store_true",
        help="grant every write without asking. Logged as such.",
    )
    run.add_argument("--max-iterations", type=int, default=30)
    run.add_argument("--max-tokens", type=int, default=200_000)
    run.add_argument("--max-seconds", type=int, default=300)
    run.add_argument("--operator", default="operator")

    rb = sub.add_parser("rollback", help="remove a run's rows from the register")
    rb.add_argument("run_id")
    rb.add_argument("--out", type=Path, default=DEFAULT_OUT)

    hist = sub.add_parser("audit", help="print the audit log for a run")
    hist.add_argument("run_id")
    hist.add_argument("--out", type=Path, default=DEFAULT_OUT)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "rollback":
        removed = rollback_run(args.out, args.run_id)
        log = AuditLog(Path(args.out) / "audit.jsonl", args.run_id)
        log.write("register_rolled_back", rows_removed=removed)
        print(f"removed {removed} row(s) written by {args.run_id}")
        print("the audit log is unchanged: the rollback is itself an entry in it")
        return 0

    if args.command == "audit":
        log = AuditLog(Path(args.out) / "audit.jsonl", args.run_id)
        entries = log.read_run(args.run_id)
        if not entries:
            print(f"no audit entries for {args.run_id}")
            return 1
        for entry in entries:
            extra = {
                k: v
                for k, v in entry.items()
                if k not in {"ts", "run_id", "seq", "event"} and v not in (None, {}, [])
            }
            print(f"{entry['seq']:>3}  {entry['event']:<20} {extra}")
        return 0

    if args.command != "run":
        build_parser().print_help()
        return 1

    requirements = load_yaml(args.requirements)

    try:
        if args.replay:
            provider = ReplayProvider(args.replay)
        else:
            provider = LiveProvider(model=args.model)
    except ProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    run = AgentRun(
        provider=provider,
        document_path=args.report,
        requirements=requirements,
        out_dir=args.out,
        budget=RunBudget(
            max_iterations=args.max_iterations,
            max_tokens=args.max_tokens,
            max_seconds=args.max_seconds,
        ),
        auto_approve=args.approve_all,
        operator=args.operator,
    )
    result = run.run()
    print_report(result)

    if args.record and isinstance(provider, LiveProvider):
        path = provider.save_recording(args.record)
        print(f"  recorded session written to {path}\n")

    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
