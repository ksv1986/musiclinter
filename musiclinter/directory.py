import os
from functools import cached_property
from pathlib import Path
from typing import Generator

from kstools.files import lowerext

from .state import State

# File extension categories
# Using set type for fast "in" checks
LOSSLESS = (
    "alac",
    "ape",
    "flac",
    "wav",
    "wv",
)
COMPRESSED = (
    "aac",
    "m4a",
    "mp3",
    "ogg",
    "opus",
    "wma",
)
IMAGES = (
    "bmp",
    "gif",
    "jpeg",
    "jpg",
    "png",
    "tiff",
)
PLAYLIST = (
    "m3u",
    "m3u8",
)
IGNORE = (
    "",
    "avi",
    "log",
    "txt",
)


def count(d: dict, v: str) -> None:
    """Increase counter of value v in dictionary d"""
    d[v] = d.get(v, 0) + 1


def _build_analyzer():
    """
    Creates map(ext -> f(d, ext, name)) that can be used
    to put file into corresponding category
    """
    analyzer = {}

    def _increment_ignored(d, _ext, _name):
        d.ignored += 1  # Can't use assignment in lambda

    for e in IGNORE:
        analyzer[e] = _increment_ignored
    for e in LOSSLESS:
        analyzer[e] = lambda d, _ext, name: d.lossless.append(name)
    for e in COMPRESSED:
        analyzer[e] = lambda d, _ext, name: d.compressed.append(name)
    for e in IMAGES:
        analyzer[e] = lambda d, _ext, name: d.images.append(name)
    for e in PLAYLIST:
        analyzer[e] = lambda d, _ext, name: d.playlist.append(name)
    for e in ("cue",):
        analyzer[e] = lambda d, _, name: d.cue.append(name)

    return analyzer


class Directory:
    """
    Single directory state:
    - path
    - media file names categorized by types
    """

    _analyzer = _build_analyzer()
    logger = State.logger.getChild("dir")

    def __init__(self, path: Path, parent=None):
        self.path = path
        self.parent = parent
        self.lossless = []
        self.compressed = []
        self.cue = []
        self.images = []
        self.playlist = []
        self.ignored = 0
        """Number of known and ignored files"""
        self.unknown = {}
        """Extension→count map for unknown file types"""
        self.subdirs = []
        """Subdirectory names"""
        self.children = None
        """If recursive processing is on, child directories for each subdir"""

        self.analyze()

    @cached_property
    def depth(self) -> int:
        """Maximal level of (processed) included subfolders"""
        if not self.children:
            return 0
        else:
            return 1 + max(map(lambda ch: ch.depth, self.children))

    @property
    def distance(self) -> int:
        """Distance from root to current directory"""
        if not self.parent:
            return 0
        else:
            return 1 + self.parent.distance

    @property
    def recursive(self) -> bool:
        """True if directory must be processed recursively"""
        return State.recursive

    def analyze(self) -> None:
        """Enumerate all files in directory and sort them into categories"""

        it = next(os.walk(self.path))

        self.subdirs = list(it[1])
        files = it[2]

        for f in files:
            self.analyze_file(f)

        if self.recursive:
            self.children = [Directory(Path(self.path, d), self) for d in self.subdirs]

    def analyze_file(self, name: str) -> None:
        """
        Fast method:
        - Using analyzer dictionary find mapping for known files
        - If there is no mapping, count unknown file extensions
        """
        ext = lowerext(name)
        f = self._analyzer.get(ext, lambda d, ext, _: count(d.unknown, ext))
        f(self, ext, name)

    def log_summary(self, level: int) -> None:
        """Logs directory state with given logging level"""
        for line in self.summary():
            self.logger.log(level, line)
        for ext, nr in self.unknown.items():
            self.logger.log(level, f"\t{ext}: {nr}")

    def summary(self, brief: bool = True) -> Generator[str, None, None]:
        """Yields readable presentation of directory state line-by-line"""
        yield f"{self.path}:"

        def visit(self, attr: str):
            """If brief is true, yield only if attribute value is not empty"""
            val = getattr(self, attr)
            if not brief or val:
                if isinstance(val, list) or isinstance(val, dict):
                    val = len(val)
                yield f"{attr}: {val}"

        for attr in (
            "lossless",
            "compressed",
            "cue",
            "images",
            "ignored",
            "unknown",
            "subdirs",
            "depth",
            "distance",
        ):
            yield from visit(self, attr)
