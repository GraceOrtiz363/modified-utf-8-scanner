# Modified UTF-8 Scanner

A small Python library that scans byte sequences encoded in Java-style Modified UTF-8 and reports the byte span and codepoint of each character, without decoding the entire buffer.

## Usage

```python
from modified_utf_8_scanner import ModifiedUtf8Scanner, DecodeError

# 'A' (1 byte), embedded NUL (2 bytes in MUTF-8), U+20AC (3 bytes)
data = b"A\xc0\x80\xe2\x82\xac"
scanner = ModifiedUtf8Scanner(data)

while scanner:
    start, length, cp = scanner.next_span()
    print(start, length, hex(cp))

# Supplementary characters (U+10000..U+10FFFF) use six-byte surrogate pairs.
# U+1F600 encoded as high surrogate U+D83D then low surrogate U+DE00.
pair = b"\xed\xa0\xbd\xed\xb8\x80"
scanner = ModifiedUtf8Scanner(pair)
start, length, cp = scanner.next_pair_span()
# -> (0, 6, 0x1F600)
```

## Why this exists

Java's `DataInput`/`DataOutput` and the JVM class file format use Modified UTF-8, which differs from standard UTF-8 in two ways: the NUL character is encoded as `0xC0 0x80` (never a raw `0x00` byte), and supplementary characters are written as a pair of three-byte CESU-8 surrogate forms rather than a single four-byte standard-UTF-8 sequence. A scanner that only knows standard UTF-8 will misread both cases.

The trade-off here is that this library does not provide a `decode_all` convenience method. It returns spans and codepoints one at a time so callers can build their own validation, indexing, or streaming logic on top. If you want a full `bytes -> str` in one call, use the stdlib ` codecs` module with a custom codec; that is out of scope.

## Edge cases

- A raw `0x00` byte is rejected. In Modified UTF-8 the only way to represent U+0000 is `0xC0 0x80`.
- Standalone three-byte surrogates (U+D800..U+DFFF) are rejected by `next_span`. They are only legal as the two halves of a six-byte supplementary pair, which `next_pair_span` handles.
- Four-byte standard UTF-8 leads (`0xF0`..`0xF4`) raise `DecodeError`; Modified UTF-8 never uses them.
- Overlong encodings (e.g. `0xC1 0x81` for 'A') are rejected.

## API

`ModifiedUtf8Scanner(data)` — construct from any bytes-like object. Internally copies to a `bytes`.

- `.next_span(position=None)` -> `(start, length, codepoint)`. Consumes one character when `position` is `None` or equals the current position. Returns `(-1, 0, -1)` at end of data.
- `.next_pair_span(position=None)` -> `(start, length, codepoint)`. Consumes a six-byte supplementary character. Raises `DecodeError` if the bytes are not a valid high-then-low surrogate pair.
- `.pos` — current scan offset. Mutated by `next_span` / `next_pair_span` when called at the current position.
- `len(scanner)` — number of bytes remaining from `pos`.
- `bool(scanner)` — `True` if bytes remain.

`DecodeError(ValueError)` — raised on any malformed sequence.
