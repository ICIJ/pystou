import itertools
import os
import unittest

from normalize.rules import RULES, fix_utf8, normalize_name


def name_from(raw: bytes) -> str:
    """Builds the str the filesystem would hand us for these raw bytes."""
    return os.fsdecode(raw)


class TestNormalizeName(unittest.TestCase):
    def test_cesu8_emoji_is_repaired_then_removed(self):
        # 'bad_<emoji>.txt' where the emoji is a UTF-16 surrogate pair encoded
        # byte-for-byte (CESU-8), which is what the affected corpus contains.
        name = name_from(b"bad_\xed\xa0\xbd\xed\xb8\x80.txt")
        self.assertEqual(normalize_name(name), ("bad_.txt", "repaired", ["utf8", "astral"]))

    def test_unrecoverable_bytes_collapse_to_one_underscore(self):
        name = name_from(b"note_\x9f\x98.txt")
        self.assertEqual(normalize_name(name), ("note__.txt", "stripped", ["utf8"]))

    def test_nfd_is_composed_to_nfc(self):
        # Explicit combining sequence: a composed "\u00e9" literal here would
        # already be NFC and would never exercise the rule.
        new, mode, applied = normalize_name("Cafe\u0301.pdf")
        self.assertEqual(new, "Caf\u00e9.pdf")
        self.assertEqual(mode, "clean")
        self.assertEqual(applied, ["nfc"])

    def test_control_characters_become_a_single_space(self):
        self.assertEqual(normalize_name("note\nline2.pdf")[0], "note line2.pdf")

    def test_trailing_dots_and_spaces_are_trimmed(self):
        self.assertEqual(normalize_name("report. ")[0], "report")

    def test_aws_avoid_punctuation_is_removed(self):
        self.assertEqual(normalize_name("Q1 #3 [final].pdf")[0], "Q1 3 final.pdf")

    def test_astral_characters_are_removed(self):
        self.assertEqual(
            normalize_name("\U0001f195\U0001f33f Nos infusions.eml")[0], "Nos infusions.eml"
        )

    def test_bmp_symbols_are_kept(self):
        # Only codepoints above the BMP encode as surrogate pairs, so a BMP
        # symbol cannot trigger the CESU-8 path this rule exists for.
        self.assertEqual(
            normalize_name("r\u00e9union \u2705.pdf"), ("r\u00e9union \u2705.pdf", "clean", [])
        )

    def test_astral_rule_can_be_skipped(self):
        name = name_from(b"bad_\xed\xa0\xbd\xed\xb8\x80.txt")
        self.assertEqual(normalize_name(name, rules=("utf8",))[0], "bad_\U0001f600.txt")

    def test_name_of_only_astral_characters_gets_the_fallback(self):
        self.assertEqual(normalize_name("\U0001f195\U0001f33f")[0], "unnamed")

    def test_name_reduced_to_nothing_gets_the_fallback(self):
        self.assertEqual(normalize_name("###")[0], "unnamed")

    def test_clean_name_is_untouched(self):
        self.assertEqual(normalize_name("normal.pdf"), ("normal.pdf", "clean", []))

    def test_leading_dot_is_preserved(self):
        self.assertEqual(normalize_name(".hidden")[0], ".hidden")

    def test_rules_can_be_selected(self):
        # With only utf8 selected, an NFD name must be left alone.
        nfd = "Cafe\u0301.pdf"
        self.assertEqual(normalize_name(nfd, rules=("utf8",))[0], nfd)

    def test_utf8_rule_can_be_skipped(self):
        name = name_from(b"note_\x9f.txt")
        self.assertEqual(normalize_name(name, rules=("nfc",))[0], name)


class TestIdempotence(unittest.TestCase):
    def test_normalizing_twice_changes_nothing(self):
        names = [
            name_from(b"bad_\xed\xa0\xbd\xed\xb8\x80.txt"),
            name_from(b"note_\x9f\x98.txt"),
            "Cafe\u0301.pdf",
            "note\nline2.pdf",
            "report. ",
            "Q1 #3 [final].pdf",
            "###",
            ".hidden",
            "normal.pdf",
        ]
        for name in names:
            with self.subTest(name=repr(name)):
                once = normalize_name(name)[0]
                self.assertEqual(normalize_name(once)[0], once)

    def test_idempotent_for_every_rule_subset(self):
        # Trimming runs after punctuation removal precisely so that every
        # subset stays idempotent; this is the test that pins that ordering.
        name = name_from(b"Q1 #\x9f3 [final]. ")
        for size in range(len(RULES) + 1):
            for subset in itertools.combinations(RULES, size):
                with self.subTest(rules=subset):
                    once = normalize_name(name, rules=subset)[0]
                    self.assertEqual(normalize_name(once, rules=subset)[0], once)


class TestFixUtf8(unittest.TestCase):
    def test_reports_clean_for_valid_utf8_emoji(self):
        self.assertEqual(fix_utf8("ok \U0001f600.txt"), ("ok \U0001f600.txt", "clean"))

    def test_reports_stripped_when_only_part_is_recoverable(self):
        name = name_from(b"\xed\xa0\xbd\xed\xb8\x80_\x9f.txt")
        new, mode = fix_utf8(name)
        self.assertEqual(new, "\U0001f600__.txt")
        self.assertEqual(mode, "stripped")


class TestUnicodeWhitespace(unittest.TestCase):
    def test_non_ascii_spaces_are_left_alone(self):
        # NBSP and the ideographic space are valid, S3-safe UTF-8: the control
        # rule is scoped to C0/C1 controls and trailing spaces and dots.
        for name in ("a\xa0b.txt", "a\u3000b.txt"):
            with self.subTest(name=repr(name)):
                self.assertEqual(normalize_name(name), (name, "clean", []))

    def test_a_leading_nbsp_is_not_stripped(self):
        self.assertEqual(normalize_name("\xa0note.txt")[0], "\xa0note.txt")


class TestAppliedRules(unittest.TestCase):
    def test_trailing_space_exposed_by_punct_removal_is_credited_to_control(self):
        # Punctuation removal can expose a trailing space that only the final
        # trim clears; the rule that changed the name must still be reported.
        new, _mode, applied = normalize_name("a #")
        self.assertEqual(new, "a")
        self.assertIn("control", applied)
