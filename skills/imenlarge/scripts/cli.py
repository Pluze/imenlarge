"""Prepare a reconstruction prompt or review generated frames against their source."""
import argparse
import sys
from importlib.metadata import version


def main():
    parser = argparse.ArgumentParser(prog="imenlarge", description=__doc__)
    parser.add_argument("--version", action="version", version=version("imenlarge"))
    parser.add_argument("command", choices=("prompt", "review", "match-tone", "focus"))
    args = parser.parse_args(sys.argv[1:2])
    if args.command == "prompt":
        from .prompt import main as command
    elif args.command == "focus":
        from .focus import main as command
    elif args.command == "match-tone":
        from .tone import main as command
    else:
        from .review import main as command
    command(sys.argv[2:])
