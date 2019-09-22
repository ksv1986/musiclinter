#!/usr/bin/env python3

import os
import sys

import chardet
from colorama import Fore

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
IGNORE = frozenset([
    '',
    'avi',
    'log',
    'm3u',
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

W = Fore.YELLOW
I = Fore.GREEN
R = Fore.RESET


def fileextlow(name):
    e = os.path.splitext(name)[1].lower()
    return e[1:] if e else ''


class Processor:
    def __init__(self, verbose=False, recursive=False):
        self.verbose = verbose
        self.recursive = recursive


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
        self.subdirs = []

    def _analyze(self):
        """Enumerate all files in directory and sort them into categories"""
        for _, self.subdirs, files in os.walk(self.path):
            for f in files:
                self._analyze_file(fileextlow(f), f)
            break  # stop walk() from entering subdirectories

    def _analyze_file(self, ext, name):
        """
        Fast method:
        - Using analyzer dictionary find mapping for known files
        - If there is no mapping, put file extension into unknown set
        """
        f = self._analyzer.get(ext, lambda d, ext, _: d.unknown.add(ext))
        f(self, ext, name)

    def process(self):
        self._analyze()

        if self.p.verbose:
            self.print_summary()

        self._process()

        if self.p.recursive and self.subdirs:
            for d in self.subdirs:
                Directory(self.p, os.path.join(self.path, d)).process()

    def _process(self):
        pass

    def print_summary(self):
        print(f"{self.path}:")
        print(f"lossless: {len(self.lossless)}")
        print(f"compressed: {len(self.compressed)}")
        print(f"cue: {len(self.cue)}")
        print(f"images: {len(self.images)}")
        print(f"ignored: {self.ignored}")
        print(f"dirs: {len(self.subdirs)}")
        print(f"unknown: {self.unknown}")


def process_dir(path, **kwargs):
    Directory(Processor(**kwargs), path).process()


def process_cue_data(cue, files, data):
    dirty = False
    r = chardet.detect(data)
    print("%s:" % (cue))
    e = r['encoding']
    encoding = ENCODING_MAP.get(e, e)
    if e not in CUE_ENCODING:
        print(f"Invalid encoding {W}{e}{R}")
        dirty = True
    content = data.decode(encoding)
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('FILE'):
            parts = line.split('"')
            if len(parts) != 3:
                raise Exception(line)
            filename = parts[1]
            if filename not in files:
                basename = os.path.splitext(filename)
                for f in files:
                    if f.startswith(basename):
                        print(f"Invalid filename {W}{filename}{R}, shoule be {I}{f}{R}")
                        content.replace(filename, f)
                        filename = f
                        dirty = True
                        break
                    else:
                        raise Exception(f"{cue} for nonexistent file {filename}")
            break
    else:
        raise Exception(f"cue file {cue} doesn't have FILE line")
    if dirty:
        linted = cue[:-3] + 'linted.cue'
        with open(linted, 'wb') as f:
            f.write(content.encode('UTF-8-SIG'))
            print(f"Saved CUE file as {W}{linted}{R}")
    else:
        print(f"CUE file {I}{cue}{R} is {I}OK{R}")


def process_cue(cue, files):
    with open(cue, 'rb') as f:
        process_cue_data(cue, files, f.read())


if __name__ == '__main__':
    process_dir(sys.argv[1], verbose=True)
