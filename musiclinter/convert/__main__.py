import logging
import os
from pathlib import Path
from subprocess import CalledProcessError

from . import (
    Converter,
    L,
)


def convert_single(conv: Converter, path: Path) -> None:
    try:
        conv.convert_dir(path)
    except (
        CalledProcessError,
        NotImplementedError,
        FileExistsError,
    ) as ex:
        L.error(f"{path}: {ex}")


def convert_recursive(conv: Converter, source: Path) -> None:
    convert_single(conv, source)
    for root, dirs, _ in os.walk(source):
        for d in dirs:
            convert_single(conv, Path(root, d))


def parse_args():
    from argparse import ArgumentParser

    p = ArgumentParser("musiconv")
    p.add_argument("source", nargs="+", type=Path)
    p.add_argument("-d", "--dest", type=Path)
    p.add_argument("-r", "--recursive", action="store_true")
    return p.parse_args()


def main():
    logging.basicConfig()
    L.setLevel(logging.DEBUG)

    args = parse_args()

    conv = Converter()

    convert = convert_recursive if args.recursive else convert_single
    for path in args.source:
        conv.destination = args.dest or path
        convert(conv, path)


if __name__ == "__main__":
    main()
