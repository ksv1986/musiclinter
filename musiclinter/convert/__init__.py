from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from multiprocessing import cpu_count
from pathlib import Path, PurePath
from subprocess import check_call

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


class Lossy(Exception):
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


class Converter:
    destination: Path = None
    genre: str = ""
    year: str = ""
    enc: Codec = Codec.default()

    def timestamp(self) -> str:
        return f"{datetime.now():%Y-%m-%d %H-%M}"

    def convert_lossless(self, source: Path, files: list[str]) -> Path:
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
        dest.mkdir(parents=True)

        get_name = va_name if multi_artist else single_name

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

    def convert_cue(self, source: Path, lossless: list[str], cues: list[str]) -> Path:
        cue = cues[0]
        input = Path(source, lossless[0])
        path = Path(source, cue)

        c = Cue(str(path), path.read_bytes())

        c.genre = c.genre or self.genre
        c.date = year_string(c.date, self.year)

        album_dir = c.title
        if c.date:
            album_dir = " - ".join((c.date, album_dir)) if album_dir else c.date
        album_dir = album_dir or self.timestamp()

        dest = PurePath(c.performer) / album_dir
        L.debug(f"dest={dest}")
        L.debug(f"artist={c.performer}")
        L.debug(f"album={album_dir}")
        L.debug(f"date={some(c.date)}")
        L.debug(f"genre={some(c.genre)}")

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
            # File name matches %n
            name = f"{t.index:02}.{ext}"
            file = dest / name

            # Add tags to split and encoded tracks
            with TagFile(file, save_on_exit=True) as f:
                f.tags["ALBUM"] = c.title
                f.tags["TRACKNUMBER"] = f"{t.index:02}"
                f.tags["TITLE"] = t.title

                if not t.performer or t.performer == c.performer:
                    f.tags["ARTIST"] = c.performer
                else:
                    f.tags["ARTIST"] = t.performer
                    f.tags["ALBUMARTIST"] = c.performer
                if c.date:
                    f.tags["DATE"] = str(c.date)
                if c.genre:
                    f.tags["GENRE"] = c.genre

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

        if d.compressed:
            raise Lossy(f"{source}: {len(d.compressed)} compressed files")

        msg = source.absolute().name if str(source) == "." else source
        L.debug(msg)

        if len(d.lossless) > 1 or not d.cue:
            return self.convert_lossless(source, d.lossless)

        return self.convert_cue(source, d.lossless, d.cue)
