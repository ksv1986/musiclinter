from datetime import datetime
from typing import Iterator, Optional

min_year = 1960
max_year = datetime.now().year + 1


def digit_substr(s: str) -> Iterator[str]:
    begin = 0
    for i in range(0, len(s)):
        if not s[i].isdigit():
            if begin < i:
                yield s[begin:i]
            begin = i + 1
    if begin < len(s):
        yield s[begin:]


def is_year(y: int) -> bool:
    return y >= min_year and y <= max_year


def string_to_years(s: str) -> list[int]:
    """Find all numbers that look like year in given string"""
    numbers = map(int, filter(lambda y: len(y) == 4, digit_substr(s)))
    return list(filter(is_year, numbers))


def guess_year(name: str) -> Optional[int]:
    """If name contains something that looks like a year, return it"""
    years = string_to_years(name)
    return years[0] if len(years) == 1 else None


def year_string(name: str, default: str = "") -> str:
    n = guess_year(name)
    return str(n) if n else default
