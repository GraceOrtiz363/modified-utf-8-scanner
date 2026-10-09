import unittest

from modified_utf_8_scanner import ModifiedUtf8Scanner, DecodeError


class TestAscii(unittest.TestCase):
    def test_single_byte_ascii(self):
        s = ModifiedUtf8Scanner(b"A")
        start, length, cp = s.next_span()
        self.assertEqual((start, length, cp), (0, 1, ord("A")))
        self.assertFalse(s)

    def test_ascii_sequence_advances_position(self):
        s = ModifiedUtf8Scanner(b"abc")
        spans = []
        while s:
            spans.append(s.next_span())
        self.assertEqual(spans, [(0, 1, 97), (1, 1, 98), (2, 1, 99)])

    def test_exhaustion_returns_sentinel(self):
        s = ModifiedUtf8Scanner(b"x")
        s.next_span()
        self.assertEqual(s.next_span(), (-1, 0, -1))


class TestNullByte(unittest.TestCase):
    def test_two_byte_null(self):
        s = ModifiedUtf8Scanner(b"\xc0\x80")
        start, length, cp = s.next_span()
        self.assertEqual((start, length, cp), (0, 2, 0))

    def test_raw_zero_byte_is_rejected(self):
        s = ModifiedUtf8Scanner(b"\x00")
        with self.assertRaises(DecodeError):
            s.next_span()


class TestTwoByte(unittest.TestCase):
    def test_latin_small_letter_eth(self):
        # U+00F0 -> 0xC3 0xB0 in standard and Modified UTF-8 alike.
        s = ModifiedUtf8Scanner(b"\xc3\xb0")
        start, length, cp = s.next_span()
        self.assertEqual((start, length, cp), (0, 2, 0xF0))

    def test_overlong_two_byte_rejected(self):
        # 0xC1 0x81 decodes to 0x41, which is an overlong encoding of 'A'.
        s = ModifiedUtf8Scanner(b"\xc1\x81")
        with self.assertRaises(DecodeError):
            s.next_span()

    def test_truncated_two_byte(self):
        s = ModifiedUtf8Scanner(b"\xc3")
        with self.assertRaises(DecodeError):
            s.next_span()


class TestThreeByte(unittest.TestCase):
    def test_euro_sign(self):
        # U+20AC -> 0xE2 0x82 0xAC.
        s = ModifiedUtf8Scanner(b"\xe2\x82\xac")
        start, length, cp = s.next_span()
        self.assertEqual((start, length, cp), (0, 3, 0x20AC))

    def test_overlong_three_byte_rejected(self):
        # 0xE0 0x80 0x80 would decode to U+0000 via three bytes.
        s = ModifiedUtf8Scanner(b"\xe0\x80\x80")
        with self.assertRaises(DecodeError):
            s.next_span()

    def test_standalone_surrogate_rejected(self):
        # High surrogate U+D800 encoded as three bytes.
        s = ModifiedUtf8Scanner(b"\xed\xa0\x80")
        with self.assertRaises(DecodeError):
            s.next_span()


class TestSupplementaryPair(unittest.TestCase):
    def test_grinning_face(self):
        # U+1F600: high surrogate U+D83D, low surrogate U+DE00.
        # High: 0xED 0xA0 0xBD. Low: 0xED 0xB8 0x80.
        data = b"\xed\xa0\xbd\xed\xb8\x80"
        s = ModifiedUtf8Scanner(data)
        start, length, cp = s.next_pair_span()
        self.assertEqual((start, length, cp), (0, 6, 0x1F600))

    def test_pair_requires_high_surrogate_first(self):
        # Low surrogate first is illegal.
        s = ModifiedUtf8Scanner(b"\xed\xb8\x80\xed\xa0\xbd")
        with self.assertRaises(DecodeError):
            s.next_pair_span()

    def test_pair_truncated(self):
        s = ModifiedUtf8Scanner(b"\xed\xa0\xbd\xed\xb8")
        with self.assertRaises(DecodeError):
            s.next_pair_span()

    def test_pair_second_half_not_low_surrogate(self):
        # Both halves are three-byte BMP characters, not surrogates.
        s = ModifiedUtf8Scanner(b"\xe2\x82\xac\xe2\x82\xac")
        with self.assertRaises(DecodeError):
            s.next_pair_span()


class TestRandomAccess(unittest.TestCase):
    def test_next_span_does_not_advance_when_position_given(self):
        s = ModifiedUtf8Scanner(b"abc")
        s.next_span()  # consumes 'a', pos -> 1
        # Look ahead at position 2 without consuming.
        span = s.next_span(2)
        self.assertEqual(span, (2, 1, ord("c")))
        # pos is still 1.
        self.assertEqual(s.pos, 1)

    def test_next_pair_span_advances_when_at_current(self):
        data = b"\xed\xa0\xbd\xed\xb8\x80"
        s = ModifiedUtf8Scanner(data)
        span = s.next_pair_span()
        self.assertEqual(span, (0, 6, 0x1F600))
        self.assertEqual(s.pos, 6)


class TestInputValidation(unittest.TestCase):
    def test_non_bytes_rejected(self):
        with self.assertRaises(TypeError):
            ModifiedUtf8Scanner("not bytes")

    def test_bytearray_accepted(self):
        s = ModifiedUtf8Scanner(bytearray(b"hello"))
        self.assertEqual(s.next_span(), (0, 1, ord("h")))


class TestIllegalLead(unittest.TestCase):
    def test_four_byte_lead_rejected(self):
        # Standard UTF-8 four-byte form is illegal in Modified UTF-8.
        s = ModifiedUtf8Scanner(b"\xf0\x90\x80\x80")
        with self.assertRaises(DecodeError):
            s.next_span()

    def test_fe_lead_rejected(self):
        s = ModifiedUtf8Scanner(b"\xfe")
        with self.assertRaises(DecodeError):
            s.next_span()


if __name__ == "__main__":
    unittest.main()
