from typing import Iterator

from .directory import Directory
from .state import State

__all__ = [
    "Directory",
    "Linter",
    "State",
]


class Linter:
    """Base class to perform linting on single music directory
    Linting is performed after directory (and its children in recursive mode)
    were analyzed - so files are already sorted into categories.
    The job of concrete linter is to identify any problems and optionally fix them.
    """

    def lint(self, d: Directory) -> None:
        pass

    def summary(self, brief: bool = True) -> Iterator[str]:
        pass
