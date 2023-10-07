from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from multiprocessing import cpu_count
from pathlib import Path, PurePath
from shutil import copyfile
from subprocess import check_call
from typing import Callable, Tuple

from kstools.cue import Cue

from ..dates import year_string
from ..directory import Directory
from ..state import State
from ..tag import Tag, TagFile
from .codec import Codec

L = State.logger.getChild("convert")
VA = "VA"
"""Varios artists placeholder name"""
VARIOUS = "Various"
"""Various tag values placeholder"""
NONE = "-"
"""Placeholder for empty tag value"""


class NotDir(Exception):
    pass


def some(v: str, multi: bool = False) -> str:
    if multi:
        return VARIOUS
    elif v:
        return v
    else:
        return NONE


def safe_name(v: str) -> str:
    """Replace or delete symbols not usable in Windows file names"""
    out = ""
    for c in v:
        match c:
            case ":" | "/":
                out += "-"
            case "\\":
                out += "_"
            case _ if c < " ":
                pass
            case _ if c in '<>:"|?*':
                pass
            case x:
                out += x
    return out


def name_prefix(t: Tag) -> str:
    return f"{int(t.track):02}. " if t.track else ""


def single_name(t: Tag) -> str:
    return name_prefix(t) + t.title


def va_name(t: Tag) -> str:
    return name_prefix(t) + t.artist + " - " + t.title


NameFn = Callable[[Tag], str]
ParsedTags = Tuple[Path, list[Tag], NameFn]


class Converter:
    destination: Path = None
    genre: str = ""
    year: str = ""
    enc: Codec = Codec.default()

    def timestamp(self) -> str:
        return f"{datetime.now():%Y-%m-%d %H-%M}"

    def copyfile(self, src: Path, dst: Path) -> None:
        msg = f"{src.name}"
        if src.name != dst.name:
            msg += f" → {dst.name}"
        L.info(msg)
        copyfile(src, dst)

    def copy_images(self, source: Path, dest: Path, images: list[str]) -> None:
        for image in images:
            self.copyfile(source / image, dest / image)

    def read_tags(self, source: Path, files: list[str]) -> ParsedTags:
        year = year_string(source.name, self.year)
        tags = [Tag.read(source / f, year=year, genre=self.genre) for f in files]

        first = tags[0]
        prev_album = first.album
        prev_artist = first.artist
        prev_year = first.year
        prev_genre = first.genre

        multi_album = False
        multi_artist = False
        multi_year = False
        multi_genre = False
        for t in tags[1:]:
            multi_album = multi_album or prev_album != t.album
            multi_artist = multi_artist or prev_artist != t.artist
            multi_year = multi_year or prev_year != t.year
            multi_genre = multi_genre or prev_genre != t.genre

            prev_album = t.album
            prev_artist = t.artist
            prev_year = t.year
            prev_genre = t.genre

        artist_dir = VA if multi_artist else safe_name(prev_artist)
        album_dir = self.timestamp() if multi_album else safe_name(prev_album)
        if not multi_year and prev_year:
            album_dir = safe_name(prev_year) + " - " + album_dir

        dest = PurePath(artist_dir) / album_dir
        L.debug(f"dest={dest}")
        L.debug(f"artist={some(prev_artist, multi_artist)}")
        L.debug(f"album={some(prev_album, multi_album)}")
        L.debug(f"date={some(prev_year, multi_year)}")
        L.debug(f"genre={some(prev_genre, multi_genre)}")

        dest = self.destination / dest
        get_name = va_name if multi_artist else single_name

        return dest, tags, get_name

    def convert_lossless(self, source: Path, files: list[str]) -> Path:
        dest, tags, get_name = self.read_tags(source, files)
        dest.mkdir(parents=True)

        enc = self.enc
        with ThreadPoolExecutor(max_workers=cpu_count()) as pool:
            for t in tags:
                name = safe_name(get_name(t)) + "." + enc.ext()
                out = dest / name

                L.info(f"{t.path.stem} -> {name}")
                cmd = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "1",
                    "-i",
                    t.path,
                    *enc.ffmpeg_args(),
                    out,
                ]
                pool.submit(check_call, cmd)

        # ffmpeg leaves terminal with invisible cursor, reset tty
        check_call(["stty", "sane"])

        return dest

    def copy_lossy(self, source: Path, lossy: list[str]) -> Path:
        dest, tags, get_name = self.read_tags(source, lossy)
        dest.mkdir(parents=True)

        for t in tags:
            name = safe_name(get_name(t))
            out = dest / (name + t.path.suffix)
            self.copyfile(t.path, out)

        return dest

    def convert_cue(self, source: Path, lossless: list[str], cues: list[str]) -> Path:
        cue = cues[0]
        input = Path(source, lossless[0])
        path = Path(source, cue)

        c = Cue(str(path), path.read_bytes())

        performer = c.performer
        genre = c.genre or self.genre
        album = c.title
        date = year_string(c.date, self.year)

        # Strip spaces
        performer = performer.strip()
        genre = genre.strip()
        album = album.strip()
        date = date.strip()

        album_dir = album
        if date:
            album_dir = " - ".join((date, album_dir)) if album_dir else date
        album_dir = album_dir or self.timestamp()

        dest = PurePath(performer) / album_dir
        L.debug(f"dest={dest}")
        L.debug(f"artist={performer}")
        L.debug(f"album={album_dir}")
        L.debug(f"date={some(date)}")
        L.debug(f"genre={some(genre)}")

        dest = self.destination / dest
        dest.mkdir(parents=True)

        # Run shnsplit with our codec arguments and predictable file name
        enc = self.enc
        cmd = [
            "shnsplit",
            "-d",
            dest,
            "-f",
            path,
            "-o",
            enc.shn_args(),
            "-t",
            "%n",
            input,
        ]
        check_call(cmd)

        ext = enc.ext()
        for t in c.tracks:
            # Strip spaces
            if t.performer:
                t.performer = t.performer.strip()
            t.title = t.title.strip()

            # File name matches %n
            name = f"{t.index:02}.{ext}"
            file = dest / name
            # Add tags to split and encoded tracks
            with TagFile(file, save_on_exit=True) as f:
                f.tags["ALBUM"] = album
                f.tags["TRACKNUMBER"] = f"{t.index:02}"
                f.tags["TITLE"] = t.title

                if not t.performer or t.performer == performer:
                    f.tags["ARTIST"] = performer
                else:
                    f.tags["ARTIST"] = t.performer
                    f.tags["ALBUMARTIST"] = performer
                if c.date:
                    f.tags["DATE"] = str(date)
                if c.genre:
                    f.tags["GENRE"] = genre

            # Choose desired final name for encoded file and rename
            track_artist = ""
            if t.performer and t.performer != c.performer:
                track_artist = f"{t.performer} - "

            new_name = safe_name(f"{t.index:02}. {track_artist}{t.title}.{ext}")
            file.rename(file.with_name(new_name))

        return dest

    def convert_dir(self, source: Path) -> Path:
        if not source.is_dir():
            raise NotDir(f"{source}: not a directory")

        d = Directory(source)
        if not d.lossless and not d.compressed:
            return

        msg = source.absolute().name if str(source) == "." else source
        L.debug(msg)

        if d.compressed:
            dest = self.copy_lossy(source, d.compressed)
        elif len(d.lossless) > 1 or not d.cue:
            dest = self.convert_lossless(source, d.lossless)
        else:
            dest = self.convert_cue(source, d.lossless, d.cue)

        self.copy_images(source, dest, d.images)

        return dest
