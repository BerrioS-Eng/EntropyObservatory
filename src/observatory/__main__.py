"""
Entry point: `python -m observatory [--pcap PATH]`
"""
import argparse
import sys
from pathlib import Path

from observatory.app import run


def main() -> int:
    parser = argparse.ArgumentParser(prog="observatory")
    parser.add_argument(
        "--pcap", type=Path, default=None,
        help="Pcap por defecto para modo Replay."
    )
    args = parser.parse_args()
    return run(default_pcap=args.pcap)


if __name__ == "__main__":
    sys.exit(main())