import logging
from typing import Type


class State:
    """
    Global linting state:
    - paths to process
    - options
    - common logger
    """

    logger = logging.getLogger("muslint")
    recursive: bool = False
    linters: list = []

    def enable(linter: Type):
        if linter not in State.linters:
            State.linters.append(linter)
