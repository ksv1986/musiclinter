from pathlib import Path, PureWindowsPath
from typing import Iterator

from colorama import Fore
from kstools.cue import Cue

from . import Linter
from .dates import year_string
from .directory import Directory
from .state import State

__all__ = ["CueLinter"]


L = State.logger.getChild("cue")
W = Fore.YELLOW
E = Fore.RED
I = Fore.GREEN  # noqa: E741
R = Fore.RESET


class CueLinter(Linter):
    """CueLinter can fix the following problems:
    - invalid encoding of .cue file (only ASCII and UTF-8 with BOM are considered valid)
    - invalid name of audio file (for example .wav instead of .flac)
    - leftover .cue file in directory without any media files
    """

    delete: bool = False
    fix: bool = False
    overwrite: bool = False

    def __init__(self):
        self.nr_invalid = 0
        self.nr_deleted = 0
        self.nr_fixed = 0

    def lint(self, d: Directory) -> None:
        no_music = not (d.lossless or d.compressed or d.unknown)

        for cue in d.cue:
            pretty = d.pretty(cue)
            if no_music:
                if self.delete:
                    print(f"{pretty}: no music files, removing cue file")
                    d.fullpath(cue).unlink()
                    self.nr_deleted += 1
                else:
                    print(f"{pretty}: no music files")
            else:
                self.process_cue(d.fullpath(cue), d.lossless)

    def process_cue(self, path: Path, files: list[str]) -> bool:
        data = path.read_bytes()
        cue = Cue(str(path), data)

        if cue.nr_files > 1:
            m = (
                f"{W}{path}{R}: {cue.nr_files} {W}FILE{R} statements"
                f" ({len(files)} files in directory)"
            )
            L.debug(m)

        for track in cue.tracks:
            if not track.file:
                continue

            if track.file in files:
                continue

            # Filename specified in CUE doesn't exists.
            # There is a lot of CUE files made for a WAV file that was
            # converted to some lossless format.
            # So maybe there is a compressed file with same name
            # but different extension?
            stem = PureWindowsPath(track.file).stem
            for f in files:
                if f.startswith(stem):
                    m = (
                        f"{W}{path}{R}#{track.index}: "
                        f"FILE {W}'{track.file}'{R}, should be {I}'{f}'{R}"
                    )
                    L.info(m)
                    track.file = f
                    cue.valid = False
                    cue.can_fix = True
                    break
            else:
                m = (
                    f"{W}{path}{R}#{track.index}: "
                    f"FILE {E}'{track.file}'{R} does not exist"
                )
                L.error(m)
                cue.valid = False
                cue.can_fix = False

        if cue.valid:
            L.debug(f"{I}{path}{R}: CUE file is {I}OK{R}")
            return

        self.nr_invalid += 1

        if cue.can_fix and CueLinter.fix:
            if CueLinter.overwrite:
                path.rename(path + ".bak")
                new_name = path
            else:
                new_name = path.with_suffix(".lint.cue")

            if not cue.date:
                year = year_string(path.parent.name)
                if year:
                    cue.rem_update("date", year)

            new_name.write_bytes(cue.utf8())
            L.info(f"{I}{new_name}{R}: Saved new CUE file")
            self.nr_fixed += 1

        # Since we are counting invalid files,
        # return False even though file was fixed.
        return False

    def summary(self, brief: bool = True) -> Iterator[str]:
        if self.nr_invalid or not brief:
            yield f"cue:invalid: {self.nr_invalid}"
        if self.nr_fixed or not brief:
            yield f"cue:fixed: {self.nr_fixed}"
        if self.nr_deleted or not brief:
            yield f"cue:deleted: {self.nr_deleted}"
