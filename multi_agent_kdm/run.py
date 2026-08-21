import argparse
import os
import sys
from pathlib import Path

from .orchestrator import MultiAgentOrchestrator


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert COBOL source to KDM XML.")
    parser.add_argument(
        "source", nargs="?", help="COBOL source file; stdin when omitted"
    )
    parser.add_argument("-o", "--output", help="Output XML file; stdout when omitted")
    args = parser.parse_args()

    source = (
        Path(args.source).read_text(encoding="utf-8")
        if args.source
        else sys.stdin.read()
    )
    if not source.strip():
        parser.error("No COBOL source was provided.")

    orchestrator = MultiAgentOrchestrator(api_key=os.getenv("GEMINI_API_KEY"))
    xml = orchestrator.run(source)
    if args.output:
        Path(args.output).write_text(xml, encoding="utf-8")
    else:
        print(xml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
