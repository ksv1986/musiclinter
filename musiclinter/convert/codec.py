from typing import Self


class Codec:
    """Base class to represent external codec used by shnsplit and/or ffmpeg"""

    default: Self = None

    def ext(self) -> str:
        """File extension for compressed files"""
        pass

    def shn_args(self) -> str:
        """Command line arguments to be passed to shnsplit"""
        pass

    def ffmpeg_args(self) -> list[str]:
        """Command line arguments to be passed to ffmpeg"""
        pass


class OpusCodec(Codec):
    def __init__(self, bitrate: int = 128):
        self.bitrate = bitrate
        """kbps"""

    def ext(self) -> str:
        return "opus"

    def shn_args(self) -> str:
        return f"cust ext={self.ext()} " f"opusenc --bitrate {self.bitrate} -- - %f"

    def ffmpeg_args(self) -> list[str]:
        return ["-c:a", "libopus", "-b:a", str(self.bitrate * 1000)]


Codec.default = OpusCodec
