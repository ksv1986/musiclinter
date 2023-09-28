#!/usr/bin/env python3

import argparse
import logging
import pathlib

from colorama import init

from . import Directory, State
from .covers import CoverLinter
from .cue import CueLinter


def parse_cue(val: str) -> None:
    opts = val.split(",")
    for o in opts:
        match o:
            case "fix":
                CueLinter.fix = True
            case "delete":
                CueLinter.delete = True
            case "overwrite":
                CueLinter.overwrite = True
            case "!":
                pass
            case other:
                raise argparse.ArgumentTypeError(f"unknown option: {other}")
    State.enable(CueLinter)


def parse_args():
    parser = argparse.ArgumentParser(
        "musiclinter", formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("paths", type=str, nargs="+")
    parser.add_argument("-r", "--recursive", action="store_true")
    help = """Usage: --cue OPTION[,OPTION2]...
Analyze cue files. Available options:
    fix         fix invalid cue files. Default: only report.
    delete      delete cue for non-existent media files. Default: no.
    overwrite   fix cue files in-place. Default: create new file.
Examples:
    --cue !
    --cue delete
    --cue fix,overwrite"""
    parser.add_argument("--cue", type=parse_cue, help=help)
    parser.add_argument("--covers", action="store_true")
    parser.parse_args(namespace=State)
    if State.covers:
        State.enable(CoverLinter)
    return State


def log(d: Directory):
    d.log_summary(logging.INFO)
    for c in d.children:
        log(c)


def main():
    init()
    logging.basicConfig()
    State.logger.setLevel(logging.DEBUG)

    args = parse_args()

    for path in args.paths:
        d = Directory(pathlib.Path(path))
        log(d)


if __name__ == "__main__":
    main()
