"""Entry point: `python -m observatory`."""
import sys

from observatory.app import run


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
