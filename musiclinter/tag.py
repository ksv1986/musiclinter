from dataclasses import dataclass
from pathlib import Path
from typing import Self

from taglib import File as TagFile


def gettag(f: TagFile, name: str) -> str:
    v = f.tags.get(name, [""])
    return v[0] if isinstance(v, list) else str(v)


def guess_tracknumber(name: str) -> str:
    for i in range(len(name)):
        if name[i].isdigit():
            name = name[i:]
            break
    else:
        return ""
    if len(name) == 1 or not name[1].isdigit():
        return name[0:1]
    if len(name) == 2 or not name[2].isdigit():
        return name[0:2]
    return ""


@dataclass
class Tag:
    path: Path
    track: str
    title: str
    artist: str
    albumartist: str
    album: str
    year: str
    genre: str

    def read(path: Path, /, year: str = "", genre: str = "") -> Self:
        with TagFile(path) as f:
            title = gettag(f, "TITLE") or path.stem
            return Tag(
                path,
                gettag(f, "TRACKNUMBER") or guess_tracknumber(path.stem),
                title,
                gettag(f, "ARTIST"),
                gettag(f, "ALBUMARTIST"),
                gettag(f, "ALBUM"),
                gettag(f, "DATE") or year,
                gettag(f, "GENRE") or genre,
            )
