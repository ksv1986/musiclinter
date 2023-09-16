#!/usr/bin/env python3

import argparse
import logging
import pathlib

from colorama import init

import musiclinter as ml


def parse_args():
    parser = argparse.ArgumentParser("musiclinter")
    parser.add_argument("paths", type=str, nargs="+")
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.parse_args(namespace=ml.State)
    return ml.State


def log(d: ml.Directory):
    d.log_summary(logging.INFO)
    for c in d.children:
        log(c)


def main():
    init()
    logging.basicConfig()
    ml.State.logger.setLevel(logging.DEBUG)

    args = parse_args()

    for path in args.paths:
        d = ml.Directory(pathlib.Path(path))
        log(d)


if __name__ == "__main__":
    main()
