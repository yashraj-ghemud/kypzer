"""Simplified AIFF/AIFF-C reader compatible with Python 3.13.

This module implements only the functionality required by
`speech_recognition`, namely the ``open`` factory returning an object
with ``getnchannels()``, ``getsampwidth()``, ``getframerate()``,
``getnframes()``, ``readframes()``, ``setpos()``, and ``tell()``.

It supports standard PCM AIFF/AIFF-C chunks. Compression types other
than ``NONE`` raise ``Error``.
"""

from __future__ import annotations

import builtins
import io
import struct
from collections import namedtuple

__all__ = ["Error", "open"]


class Error(Exception):
    """Raised when the parser encounters an invalid AIFF/C structure."""


def _read_str4(file) -> bytes:
    data = file.read(4)
    if len(data) != 4:
        raise EOFError("unexpected EOF while reading 4-byte chunk id")
    return data


def _read_ulong(file) -> int:
    raw = file.read(4)
    if len(raw) != 4:
        raise EOFError("unexpected EOF while reading uint32")
    return struct.unpack(">I", raw)[0]


def _read_ushort(file) -> int:
    raw = file.read(2)
    if len(raw) != 2:
        raise EOFError("unexpected EOF while reading uint16")
    return struct.unpack(">H", raw)[0]


def _read_short(file) -> int:
    raw = file.read(2)
    if len(raw) != 2:
        raise EOFError("unexpected EOF while reading int16")
    return struct.unpack(">h", raw)[0]


def _read_extended_float(file) -> float:
    # Parse 10-byte IEEE 80-bit extended precision float used in AIFF rate
    raw = file.read(10)
    if len(raw) != 10:
        raise EOFError("unexpected EOF while reading extended float")
    expon, himant, lomant = struct.unpack(">HII", raw)
    if expon == himant == lomant == 0:
        return 0.0
    sign = 1
    if expon & 0x8000:
        sign = -1
        expon &= 0x7FFF
    if expon == 0x7FFF:
        return float("inf") * sign
    expon -= 16383
    mant = (himant << 32) | lomant
    return sign * mant / (1 << 63) * pow(2.0, expon)


def _read_pstring(file) -> bytes:
    length_raw = file.read(1)
    if not length_raw:
        raise EOFError("unexpected EOF while reading pstring length")
    length = length_raw[0]
    data = file.read(length)
    if len(data) != length:
        raise EOFError("unexpected EOF while reading pstring content")
    if (length + 1) % 2 == 1:
        # pad byte for even alignment
        file.read(1)
    return data


_aifc_params = namedtuple(
    "_aifc_params",
    "nchannels sampwidth framerate nframes comptype compname",
)


class _AiffReader:
    def __init__(self, file_obj):
        self._file = file_obj
        self._params = None
        self._ssnd_pos = None
        self._frame_size = 0
        self._soundpos = 0
        self._parse_header()

    # Public API used by speech_recognition
    def getparams(self):
        return self._params

    def getnchannels(self):
        return self._params.nchannels

    def getsampwidth(self):
        return self._params.sampwidth

    def getframerate(self):
        return self._params.framerate

    def getnframes(self):
        return self._params.nframes

    def getcomptype(self):
        return self._params.comptype

    def getcompname(self):
        return self._params.compname

    def readframes(self, n):
        if self._ssnd_pos is None:
            raise Error("SSND chunk missing in AIFF file")
        self._ensure_ssnd_position()
        to_read = n * self._frame_size
        data = self._file.read(to_read)
        frames = len(data) // self._frame_size
        self._soundpos += frames
        return data

    def rewind(self):
        self.setpos(0)

    def tell(self):
        return self._soundpos

    def setpos(self, pos):
        if pos < 0 or pos > self._params.nframes:
            raise Error("position out of range")
        self._soundpos = pos
        self._file.seek(self._ssnd_pos + pos * self._frame_size)

    def close(self):
        if self._file:
            self._file.close()
            self._file = None

    # Internal helpers
    def _parse_header(self):
        if self._file.read(4) != b"FORM":
            raise Error("file does not start with FORM chunk")
        _ = _read_ulong(self._file)  # total size (unused)
        form_type = self._file.read(4)
        if form_type not in {b"AIFF", b"AIFC"}:
            raise Error("not an AIFF/AIFC file")
        self._aifc = form_type == b"AIFC"
        comm_found = False
        ssnd_found = False
        while True:
            try:
                chunk_id = _read_str4(self._file)
            except EOFError:
                break
            chunk_size = _read_ulong(self._file)
            chunk_start = self._file.tell()
            if chunk_id == b"COMM":
                self._read_comm(chunk_size)
                comm_found = True
            elif chunk_id == b"SSND":
                self._read_ssnd(chunk_size)
                ssnd_found = True
            else:
                # skip unrelated chunk
                self._file.seek(chunk_size, io.SEEK_CUR)
            # Chunks are padded to even length
            if chunk_size % 2 == 1:
                self._file.seek(1, io.SEEK_CUR)
            if comm_found and ssnd_found:
                break
        if not comm_found or not ssnd_found:
            raise Error("COMM or SSND chunk missing in AIFF file")

    def _read_comm(self, chunk_size):
        nchannels = _read_ushort(self._file)
        nframes = _read_ulong(self._file)
        sampwidth_bits = _read_ushort(self._file)
        framerate = int(_read_extended_float(self._file))
        sampwidth = (sampwidth_bits + 7) // 8
        comptype = b"NONE"
        compname = b"not compressed"
        if self._aifc:
            comptype = self._file.read(4)
            compname = _read_pstring(self._file)
            if comptype != b"NONE":
                raise Error("compressed AIFF-C is not supported")
        self._frame_size = nchannels * sampwidth
        self._params = _aifc_params(
            nchannels,
            sampwidth,
            framerate,
            nframes,
            comptype,
            compname,
        )

    def _read_ssnd(self, chunk_size):
        offset = _read_ulong(self._file)
        blocksize = _read_ulong(self._file)
        self._ssnd_pos = self._file.tell() + offset
        self._file.seek(offset, io.SEEK_CUR)

    def _ensure_ssnd_position(self):
        expected = self._ssnd_pos + self._soundpos * self._frame_size
        if self._file.tell() != expected:
            self._file.seek(expected, io.SEEK_SET)


class _AiffFile:
    def __init__(self, f, mode):
        if mode not in {"r", "rb"}:
            raise Error("write mode not supported in compatibility shim")
        if isinstance(f, (str, bytes, bytearray)):
            file_obj = builtins.open(f, "rb")
        else:
            file_obj = f
        try:
            self._reader = _AiffReader(file_obj)
        except Exception:
            file_obj.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # Delegate required methods to reader
    def __getattr__(self, item):
        return getattr(self._reader, item)

    def close(self):
        if self._reader:
            self._reader.close()
            self._reader = None


def open(f, mode="rb"):
    """Open an AIFF/AIFC file for reading.

    Only read modes are supported. This mirrors the subset used by
    `speech_recognition` which relies on ``aifc.open(path, 'r')``.
    """
    if mode not in {"r", "rb"}:
        raise Error("only read mode supported in compatibility module")
    return _AiffFile(f, mode)
