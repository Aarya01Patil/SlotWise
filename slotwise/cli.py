import argparse
import os
from pathlib import Path

from dotenv import load_dotenv


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="SlotWise: synthetic patient scheduling and evals")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Start browser app on localhost")
    serve.add_argument(
        "--mode", choices=["live", "offline"], default=os.getenv("SLOTWISE_MODE", "live")
    )
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")
    loop = commands.add_parser(
        "eval-loop", help="Baseline → failure → policy patch → candidate → gate"
    )
    loop.add_argument("--mode", choices=["live", "offline"], default="live")
    loop.add_argument("--repeats", type=int, choices=[1, 2, 3], default=2)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        from slotwise.web import create_app

        print(
            f"SlotWise: http://127.0.0.1:{args.port} · {args.mode.upper()} · synthetic patients only"
        )
        uvicorn.run(create_app(mode=args.mode), host=args.host, port=args.port, log_level="warning")
    else:
        from slotwise.evaluation import run_loop

        try:
            report = run_loop(
                Path(".slotwise") / args.mode,
                args.mode,
                args.repeats,
                progress=lambda text: print(text, flush=True),
            )
        except ValueError as error:
            parser.exit(2, str(error) + "\n")
        print(report["evidence_notice"])
        print(
            f"Before: {report['before']['score']}/100 "
            f"({report['before']['passed']}/{report['before']['total']} pass)"
        )
        print(
            f"After:  {report['after']['score']}/100 "
            f"({report['after']['passed']}/{report['after']['total']} pass)"
        )
        print("Policy: " + ("PROMOTED" if report["promotion"]["accepted"] else "REJECTED"))
        print("Report: " + report["report_path"])
        if not report["promotion"]["accepted"]:
            parser.exit(1, report["promotion"]["reason"] + "\n")


if __name__ == "__main__":
    main()
