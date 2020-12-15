#!/usr/bin/env python3

import argparse
import os
import re
import sys
from datetime import datetime

import chardet
from colorama import Fore
from enum import IntEnum

# File extension categories
# Using set type for fast "in" checks
LOSSLESS = frozenset([
    'alac',
    'ape',
    'flac',
    'wav',
    'wv',
])
COMPRESSED = frozenset([
    'aac',
    'm4a',
    'mp3',
    'ogg',
    'opus',
    'wma',
])
IMAGES = frozenset([
    'bmp',
    'gif',
    'jpeg',
    'jpg',
    'png',
    'tiff',
])
VIDEOS = frozenset([
    'avi',
    'm1v',
    'm2v',
    'mkv',
    'mov',
    'mp4',
    'mpeg',
    'mpg',
    'vob',
    'webm',
    'wmv',
])
IGNORE = frozenset([
    '',
    'doc',
    'docx',
    'log',
    'm3u',
    'pdf',
    'rtf',
    'srt',
    'toc',
    'txt',
])

# Valid CUE file encodings
CUE_ENCODING = frozenset([
    'ascii',
    'UTF-8-SIG',
])

# Map to fix wrongly guessed encodings
ENCODING_MAP = {
    'MacCyrillic': 'windows-1251'
}

# Valid cover names:
COVER_NAMES = frozenset([
    'cover',
    'folder',
    'front',
])

W = Fore.YELLOW
I = Fore.GREEN
R = Fore.RESET


def string_to_years(s):
    """Find all numbers that look like year in given string"""
    pattern = r'\d\d\d\d'
    r = re.compile(pattern)
    min_year = 1960
    max_year = datetime.now().year + 1
    return list(filter(lambda y: y >= min_year and y <= max_year, map(int, r.findall(s))))


def guess_year(path, verbose=False):
    name = os.path.basename(path)
    years = string_to_years(name)
    if verbose:
        print(f"{I}{name}{R} -> {years}")
    return years[0] if len(years) == 1 else None


def fileextlow(name):
    e = os.path.splitext(name)[1].lower()
    return e[1:] if e else ''


def filenamelow(name):
    return os.path.splitext(name)[0].lower()


class CueFix(IntEnum):
    IGNORE = 0
    CHECK = 1
    OVERWRITE = 2
    NEW = 3


class CoverFix(IntEnum):
    IGNORE = 0
    CHECK = 1


def _prepare_print_template(template):
    """Calculates and saves length of each caption"""
    return tuple(map(lambda t: (t[0], len(t[0]), t[1]), template))


class Processor:
    _print_template = _prepare_print_template((
        ('video files', 'nr_video_files'),
        ('cue dirs', 'nr_cue'),
        ('mixed dirs', 'nr_mixed_lossless_compressed'),
        ('wrong cue', 'nr_wrong_cue'),
        ('lossy cue', 'nr_lossy_cue'),
        ('multiple cue','nr_multiple_cue'),
        ('ignored', 'nr_ignored'),
        ('no cover', 'nr_no_cover'),
        ('wrong cover', 'nr_wrong_cover_name'),
        ('unknown', 'unknown'),
        ('media dirs', 'nr_media_dirs'),
        ('no media dirs', 'nr_no_media_dirs'),
        ('lossless dirs', 'nr_lossless_dirs'),
        ('total dirs', 'nr_dirs'),
    ))
    """
    Template for printing summary: caption, field, caption length.
    Order of entries defines order of printing.
    """
    _print_max = max(map(lambda t: t[1], _print_template))
    """Maximal caption length, used for vertical alignment of summary values"""

    def __init__(self, verbose=False, recursive=False, sort=False, fix_cue=CueFix.IGNORE, covers=CoverFix.IGNORE):
        # Options
        self.verbose = verbose
        self.recursive = recursive
        self.sort = sort
        # Actions
        self.fix_cue = fix_cue
        self.fix_covers = covers
        # Statistics
        self.nr_dirs = 0
        self.nr_media_dirs = 0
        self.nr_no_media_dirs = 0
        self.nr_compressed = 0
        self.nr_lossless = 0
        self.nr_lossless_dirs = 0
        self.nr_video_files = 0
        self.nr_cue = 0
        self.nr_mixed_lossless_compressed = 0
        self.nr_wrong_cue = 0
        self.nr_lossy_cue = 0
        self.nr_multiple_cue = 0
        self.nr_ignored = 0
        self.nr_no_cover = 0
        self.nr_wrong_cover_name = 0
        self.unknown = set()

    def summary(self):
        for caption, length, field in self._print_template:
            # omit default value: must break when field names does not match template
            value = getattr(self, field)
            if value:
                alignment = " " * (self._print_max - length)
                print(f'{caption}: {alignment}{value}')

    @property
    def warn_covers(self):
        return self.fix_covers > CoverFix.IGNORE

    @property
    def warn_cue(self):
        return self.fix_cue > CueFix.IGNORE


def have_valid_cover_name(images):
    lownames = {filenamelow(name) for name in images}
    return COVER_NAMES.intersection(lownames)


def _build_analyzer():
    """
    Creates map(ext -> f(d, ext, name)) that can be used
    to put file into corresponding category
    """
    analyzer = {}
    for e in LOSSLESS:
        analyzer[e] = lambda d, _ext, name: d.lossless.append(name)
    for e in COMPRESSED:
        analyzer[e] = lambda d, _ext, name: d.compressed.append(name)
    for e in IMAGES:
        analyzer[e] = lambda d, _ext, name: d.images.append(name)
    for e in VIDEOS:
        analyzer[e] = lambda d, _ext, name: d.videos.append(name)

    def _increment_ignored(d, _ext, _name):
        d.ignored += 1  # Can't use assignment in lambda

    for e in IGNORE:
        analyzer[e] = _increment_ignored
    analyzer['cue'] = lambda d, _, name: d.cue.append(name)

    return analyzer


class Directory:
    _analyzer = _build_analyzer()

    def __init__(self, processor, path):
        self.p = processor
        self.path = path
        self.lossless = []
        self.compressed = []
        self.cue = []
        self.images = []
        self.ignored = 0
        self.unknown = set()
        self.videos = []
        self.subdirs = []

    def path_to(self, name):
        return os.path.join(self.path, name)

    def _analyze(self):
        """Enumerate all files in directory and sort them into categories"""
        for _, self.subdirs, files in os.walk(self.path):
            if self.p.sort:
                self.subdirs.sort()
                files.sort()
            for f in files:
                self._analyze_file(fileextlow(f), f)
            break  # stop walk() from entering subdirectories

        self.p.nr_dirs += 1
        if self.lossless or self.compressed or self.videos:
            if self.lossless or self.compressed:
                if not self.images:
                    if self.p.warn_covers:
                        print(f"{W}{self.path}{R}: no cover file")
                    self.p.nr_no_cover += 1
                elif not have_valid_cover_name(self.images):
                    if self.p.warn_covers:
                        print(f"{W}{self.path}{R}: wrong cover names")
                    self.p.nr_wrong_cover_name += 1
            if self.lossless:
                if self.compressed:
                    self.p.nr_mixed_lossless_compressed += 1
                else:
                    self.p.nr_lossless_dirs += 1

            if self.cue:
                if not self.lossless:
                    if self.p.warn_cue:
                        print(f"{W}{self.path}{R}: cue but no lossless files")
                    self.p.nr_lossy_cue += 1
                elif not self.compressed:
                    if len(self.cue) == 1:
                        self.p.nr_cue += 1
                    else:
                        if self.p.warn_cue:
                            print(f"{W}{self.path}{R}: {len(self.cue)} cue files")
                        self.p.nr_multiple_cue += 1

            self.p.nr_media_dirs += 1
            self.p.nr_lossless += len(self.lossless)
            self.p.nr_compressed += len(self.compressed)
            self.p.nr_video_files += len(self.videos)
            self.p.nr_ignored += self.ignored
            self.p.unknown.update(self.unknown)
        else:
            self.p.nr_no_media_dirs += 1

    def _analyze_file(self, ext, name):
        """
        Fast method:
        - Using analyzer dictionary find mapping for known files
        - If there is no mapping, put file extension into unknown set
        """
        f = self._analyzer.get(ext, lambda d, ext, _: d.unknown.add(ext))
        f(self, ext, name)

    def _guess_year(self):
        return guess_year(self.path)

    def process(self):
        self._analyze()

        if self.p.verbose:
            self.print_summary()

        self._process()

        if self.p.recursive and self.subdirs:
            for d in self.subdirs:
                Directory(self.p, self.path_to(d)).process()

    def _process(self):
        if self.p.fix_cue > CueFix.IGNORE:
            for cue in self.cue:
                if not process_cue(self.path_to(cue), self.lossless, self.p):
                    self.p.nr_wrong_cue += 1

    def print_summary(self):
        print(f"{self.path}:")
        print(f"lossless: {len(self.lossless)}")
        print(f"compressed: {len(self.compressed)}")
        print(f"cue: {len(self.cue)}")
        print(f"images: {len(self.images)}")
        print(f"videos: {len(self.videos)}")
        print(f"ignored: {self.ignored}")
        print(f"dirs: {len(self.subdirs)}")
        print(f"unknown: {self.unknown}")


def process_dir(path, **kwargs):
    p = Processor(**kwargs)
    Directory(p, path).process()
    p.summary()


def process_cue_data(cue, files, p, data):
    """Parse CUE file data and return True if no problems found"""
    ok = True
    can_fix = False
    suffix = 'fixed'

    e = chardet.detect(data)['encoding']
    encoding = ENCODING_MAP.get(e, e)
    if e not in CUE_ENCODING:
        print(f"{W}{cue}{R}: Invalid encoding {W}{e}{R}")
        ok = False
        can_fix = True
        suffix = 'utf8'

    content = data.decode(encoding)

    filename = None
    date = None
    guessed_date = None
    for i, line in enumerate(content.splitlines()):
        line = line.strip()
        # print(f"{I}{cue}:{i}:{R} {line}")

        if line.startswith('FILE'):
            if filename:
                nr_files = len(files)
                print((f"{W}{cue}{R}:{i}: multiple {W}FILE{R} statements "
                       f"({nr_files} files in directory)"))
                return False

            parts = line.split('"')
            if len(parts) != 3:
                print(f"{W}{cue}{R}:{i}: cant't parse {W}FILE{R} statement")
                return False

            filename = parts[1]
        elif line.startswith('REM DATE '):
            date = line.split(' ')[2]
            if p.verbose:
                print(f"{I}{cue}{R}:{i}: DATE={date}")

    if not filename:
        print(f"{W}{cue}{R}:{i}: FILE statement not found")
        return False

    if not filename in files:
        # Filename specified in CUE doesn't exists.
        # There is a lot of CUE files made for a WAV file that was
        # converted to some lossless format.
        # So maybe there is a compressed file with same name
        # but different extension?
        basename = os.path.splitext(filename)
        for f in files:
            if f.startswith(basename):
                print((f"{W}{cue}{R}:{i}: Invalid FILE "
                       f"{W}'{filename}'{R}, should be {I}'{f}'{R}"))
                content = content.replace(filename, f)
                filename = f
                ok = False
                can_fix = True
                suffix = fileextlow(f)
                break
        else:
            print((f"{W}{cue}{R}:{i}: nonexistent FILE "
                    f"{W}'{filename}'{R}"))
            return False

    if not date:
        print(f"{W}{cue}{R}:{i}: DATE statement not found")
        guessed_date = guess_year(os.path.dirname(cue))
        if guessed_date:
            if p.verbose:
                print(f"{I}{cue}{R}: DATE {guessed_date} guessed from directory name")
        ok = False

    if not ok and can_fix and p.fix_cue > CueFix.CHECK:
        if p.fix_cue == CueFix.OVERWRITE:
            os.rename(cue, cue + '.bak')
            new_name = cue
        else:
            new_name = '.'.join([cue[:-4], suffix, 'cue'])

        if not date and guessed_date:
            content = f"REM DATE {guessed_date}\n" + content

        with open(new_name, 'wb') as f:
            f.write(content.encode('UTF-8-SIG'))
            print(f"Saved CUE file as {W}{new_name}{R}")
        # Since we are counting invalid files,
        # return False even though file was fixed.
    elif p.verbose:
        print(f"{I}{cue}{R}: CUE file is {I}OK{R}")
    return ok


def process_cue(cue, files, p):
    with open(cue, 'rb') as f:
        data = f.read()
    return process_cue_data(cue, files, p, data)


def fix_cue(cue, p):
    lossless = []
    for _, _, files in os.walk(os.path.dirname(cue)):
        if p.sort:
            files.sort()
        for f in files:
            if fileextlow(f) in LOSSLESS:
                lossless.append(f)
        break
    if not lossless:
        print(f"{W}{cue}{R}: no lossless files in directory")
        return False
    return process_cue(cue, lossless, p)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', type=str, nargs='+')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-r', '--recursive', action='store_true')
    parser.add_argument('-s', '--sort', action='store_true')
    default_fix = 'ignore'
    covers = {
        default_fix: CoverFix.IGNORE,
        'check': CoverFix.CHECK,
    }
    parser.add_argument('--covers', choices=covers.keys(), default=default_fix)
    cue = {
        default_fix: CueFix.IGNORE,
        'check': CueFix.CHECK,
        'overwrite': CueFix.OVERWRITE,
        'new': CueFix.NEW,
    }
    parser.add_argument('--cue', dest='fix_cue', choices=cue.keys(), default=default_fix)
    args = parser.parse_args()
    paths = args.paths
    args = vars(args)
    del args['paths']
    args['fix_cue'] = cue[args['fix_cue']]
    args['covers'] = covers[args['covers']]
    return paths, args


def main():
    paths, args = parse_args()
    p = Processor(**args)
    for path in paths:
        if path[-4:].lower() == '.cue':
            fix_cue(os.path.abspath(path), p)
        else:
            Directory(p, path).process()
    print('')
    p.summary()


if __name__ == '__main__':
    main()
