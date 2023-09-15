import logging


class State:
    """
    Global linting state:
    - paths to process
    - options
    - common logger
    """

    logger = logging.getLogger("muslint")
    recursive: bool = False
