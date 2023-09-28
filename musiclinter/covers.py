from typing import Iterator

from kstools.files import lowername

from . import Linter
from .directory import Directory
from .state import State

__all__ = ["CoverLinter"]


L = State.logger.getChild("cover")


class CoverLinter(Linter):
    NAMES = {
        "cover",
        "folder",
        "front",
    }

    def __init__(self):
        self.no_cover = False
        self.nr_wrong_name = 0

    def valid_names(self, images: list[str]) -> set[str]:
        lownames = {lowername(name) for name in images}
        return self.NAMES.intersection(lownames)

    def lint(self, d: Directory) -> None:
        if not d.lossless and not d.compressed:
            return
        if not d.images:
            self.no_cover = True
            L.debug(f"{d.pretty()}: no cover file")
        elif not self.valid_names(d.images):
            self.nr_wrong_name = len(d.images)
            if self.nr_wrong_name == 1:
                L.debug(f"{d.pretty(d.images[0])}: wrong cover file name")
            else:
                L.debug(
                    f"{d.pretty()}: all {self.nr_wrong_name}"
                    " images have wrong file names"
                )

    def summary(self, brief: bool = True) -> Iterator[str]:
        if self.no_cover:
            yield "cover: no cover"
        elif self.nr_wrong_name:
            yield f"cover: wrong name: {self.nr_wrong_name}"
