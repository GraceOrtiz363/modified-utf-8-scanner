from __future__ import annotations


class DecodeError(ValueError):
    """Raised when a byte sequence is not valid Modified UTF-8.

    Subclassing ValueError keeps it catchable by callers who don't care
    about the specific distinction between 'truncated' and 'illegal byte'.
    """

    pass


class ModifiedUtf8Scanner:
    """Scan a byte sequence and report the span of the next Modified UTF-8
    character, without allocating a full string decode.

    Modified UTF-8 (used by Java's DataInput/DataOutput and by the JVM
    class-file format) differs from standard UTF-8 in two ways:

    1. The U+0000 NULL is encoded as the two-byte sequence 0xC0 0x80 rather
       than the single byte 0x00. This keeps embedded data free of real NUL
       bytes so C-string style lengths remain valid.
    2. Supplementary characters (U+10000..U+10FFFF) are encoded as a
       surrogate pair of three-byte CESU-8 forms, never as the four-byte
       standard-UTF-8 encoding.

    This scanner returns, for each call to next_span, the (start, length,
    decoded_codepoint) of the character at the given position. It does not
    copy the input and never allocates a Python str beyond the one returned
    to the caller; it is intended for stream validation and indexing.
    """

    __slots__ = ("data", "pos")

    def __init__(self, data: bytes):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")
        # Normalise to a concrete bytes object. Memoryview and bytearray
        # both satisfy bytes() without copying when the source is contiguous.
        self.data = bytes(data)
        self.pos = 0

    def __len__(self) -> int:
        return len(self.data) - self.pos

    def __bool__(self) -> bool:
        return self.pos < len(self.data)

    def next_span(self, position: int | None = None) -> tuple[int, int, int]:
        """Return (start, length, codepoint) for the character at ``position``.

        Advances ``self.pos`` past the consumed bytes when ``position`` is
        None or equals the current position. When ``position`` is given
        explicitly and is behind the current position, no advance happens;
        the caller is doing random-access lookahead.

        Raises DecodeError on any malformed sequence. Returns (-1, 0, -1)
        when ``position`` is at or beyond the end of the data.
        """
        if position is None:
            position = self.pos

        if position < 0:
            raise DecodeError(f"position {position} is negative")
        if position >= len(self.data):
            return (-1, 0, -1)

        start = position
        b0 = self.data[position]

        # Single-byte ASCII: 0x01..0x7F. 0x00 is never a valid lead byte
        # in Modified UTF-8; it can only appear as the interior of the
        # two-byte NUL encoding, which is handled by the 0xC0 branch.
        if b0 == 0x00:
            raise DecodeError("raw 0x00 byte is not a valid lead in Modified UTF-8")
        if b0 <= 0x7F:
            if position == self.pos:
                self.pos += 1
            return (start, 1, b0)

        # Two-byte sequences: 0b110xxxxx 0b10xxxxxx.
        # Covers U+0000 (via 0xC0 0x80) and U+0080..U+07FF.
        if (b0 & 0xE0) == 0xC0:
            if position + 1 >= len(self.data):
                raise DecodeError("truncated two-byte sequence")
            b1 = self.data[position + 1]
            if (b1 & 0xC0) != 0x80:
                raise DecodeError(f"illegal continuation byte 0x{b1:02X}")
            cp = ((b0 & 0x1F) << 6) | (b1 & 0x3F)
            # Overlong check: the only valid value below 0x80 here is the
            # explicit NUL encoding 0xC0 0x80 -> U+0000.
            if cp == 0:
                if position == self.pos:
                    self.pos += 2
                return (start, 2, 0)
            if cp < 0x80:
                raise DecodeError("overlong two-byte sequence")
            if position == self.pos:
                self.pos += 2
            return (start, 2, cp)

        # Three-byte sequences: 0b1110xxxx 0b10xxxxxx 0b10xxxxxx.
        # Covers U+0800..U+FFFF. In Modified UTF-8 these also encode the
        # high and low surrogates that make up a six-byte supplementary form.
        if (b0 & 0xF0) == 0xE0:
            if position + 2 >= len(self.data):
                raise DecodeError("truncated three-byte sequence")
            b1 = self.data[position + 1]
            b2 = self.data[position + 2]
            if (b1 & 0xC0) != 0x80 or (b2 & 0xC0) != 0x80:
                raise DecodeError("illegal continuation byte in three-byte sequence")
            cp = ((b0 & 0x0F) << 12) | ((b1 & 0x3F) << 6) | (b2 & 0x3F)
            if 0xD800 <= cp <= 0xDFFF:
                # Surrogates are only legal as part of a six-byte
                # supplementary pair; a standalone three-byte surrogate is
                # illegal here, and the caller should use next_pair_span.
                raise DecodeError(
                    "standalone surrogate in three-byte position; "
                    "use next_pair_span for supplementary characters"
                )
            if cp < 0x800:
                raise DecodeError("overlong three-byte sequence")
            if position == self.pos:
                self.pos += 3
            return (start, 3, cp)

        raise DecodeError(f"illegal lead byte 0x{b0:02X}")

    def next_pair_span(self, position: int | None = None) -> tuple[int, int, int]:
        """Return (start, length, codepoint) for the six-byte surrogate pair
        starting at ``position``.

        Modified UTF-8 encodes supplementary characters (U+10000..U+10FFFF)
        as two consecutive three-byte sequences: the first encodes a high
        surrogate (U+DB00..U+DBFF), the second a low surrogate
        (U+DC00..U+DFFF). The reconstructed codepoint is the standard
        surrogate-pair formula.

        Raises DecodeError if the position does not hold a valid pair.
        """
        if position is None:
            position = self.pos

        if position < 0:
            raise DecodeError(f"position {position} is negative")
        if position + 5 >= len(self.data):
            raise DecodeError("not enough bytes remaining for a six-byte pair")

        b0 = self.data[position]
        if (b0 & 0xF0) != 0xE0:
            raise DecodeError("six-byte pair must begin with a three-byte lead")

        b1 = self.data[position + 1]
        b2 = self.data[position + 2]
        if (b1 & 0xC0) != 0x80 or (b2 & 0xC0) != 0x80:
            raise DecodeError("illegal continuation byte in first surrogate")
        high_cp = ((b0 & 0x0F) << 12) | ((b1 & 0x3F) << 6) | (b2 & 0x3F)
        if not (0xD800 <= high_cp <= 0xDBFF):
            raise DecodeError("first three bytes are not a high surrogate")

        b3 = self.data[position + 3]
        if (b3 & 0xF0) != 0xE0:
            raise DecodeError("second half of pair must be a three-byte lead")
        b4 = self.data[position + 4]
        b5 = self.data[position + 5]
        if (b4 & 0xC0) != 0x80 or (b5 & 0xC0) != 0x80:
            raise DecodeError("illegal continuation in second surrogate")
        low_cp = ((b3 & 0x0F) << 12) | ((b4 & 0x3F) << 6) | (b5 & 0x3F)
        if not (0xDC00 <= low_cp <= 0xDFFF):
            raise DecodeError("second three bytes are not a low surrogate")

        reconstructed = 0x10000 + ((high_cp - 0xD800) << 10) + (low_cp - 0xDC00)
        if reconstructed > 0x10FFFF:
            raise DecodeError("reconstructed codepoint exceeds U+10FFFF")

        if position == self.pos:
            self.pos += 6
        return (position, 6, reconstructed)
