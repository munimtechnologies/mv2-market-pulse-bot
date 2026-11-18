"""Tests for the run summary line: a failed run must say why, and never print a secret."""

import unittest

import mv2_config as cfg


class FakeGroup(Exception):
    """Stands in for an ExceptionGroup (forecasting-tools raises one when every prediction fails)."""

    def __init__(self, message, members):
        super().__init__(message)
        self.exceptions = tuple(members)


def wrapped(inner, url="https://www.metaculus.com/questions/1/"):
    """inner raised `from` a RuntimeError carrying the question URL, the way forecasting-tools re-raises."""
    try:
        try:
            raise inner
        except Exception as exc:
            raise RuntimeError(url) from exc
    except RuntimeError as outer:
        return outer


class RootCauseTest(unittest.TestCase):
    def test_follows_raise_from(self):
        inner = ValueError("bad numeric bounds")
        self.assertIs(cfg.root_cause(wrapped(inner)), inner)

    def test_follows_first_group_member(self):
        first = KeyError("x")
        group = FakeGroup("all predictions failed", [first, TypeError("y")])
        self.assertIs(cfg.root_cause(wrapped(group)), first)

    def test_plain_error_is_its_own_root(self):
        err = OSError("down")
        self.assertIs(cfg.root_cause(err), err)


class RedactTest(unittest.TestCase):
    def test_key_value_and_bearer(self):
        self.assertEqual(cfg.redact("api_key=sk-abc123 failed"), "api_key=*** failed")
        self.assertEqual(cfg.redact("Bearer abc"), "Bearer ***")

    def test_long_opaque_string(self):
        self.assertEqual(cfg.redact("id " + "A" * 40), "id ***")

    def test_ordinary_words_untouched(self):
        text = "max_tokens 2000 exceeded for question 12345"
        self.assertEqual(cfg.redact(text), text)


class SummaryTest(unittest.TestCase):
    def test_digest_counts_ranks_and_masks(self):
        reports = [
            object(),
            RuntimeError("q1"),
            ValueError("api_key=sk-abcdef0123456789abcdef0123456789xyz failed"),
            RuntimeError("q2"),
        ]
        digest = cfg.error_digest(reports)
        self.assertEqual(digest, "RuntimeError x2: q1; ValueError x1: api_key=*** failed")
        self.assertNotIn("abcdef0123", digest)

    def test_digest_uses_root_causes_and_collapses_whitespace(self):
        reports = [wrapped(PermissionError("403\n  Forbidden")), wrapped(PermissionError("403 again"))]
        self.assertEqual(cfg.error_digest(reports), "PermissionError x2: 403 Forbidden")

    def test_digest_empty_message_and_limit(self):
        reports = [KeyError(), TypeError("t"), OSError("o"), ValueError("v")]
        # KeyError() has an empty message; ties rank by name; only the first three kinds are named.
        self.assertEqual(cfg.error_digest(reports), "KeyError x1; OSError x1: o; TypeError x1: t")

    def test_summary_keeps_the_old_prefix(self):
        line = cfg.run_summary("tournament", [object(), RuntimeError("boom")], True)
        self.assertEqual(line, "MV2 forecast run (tournament): 1 forecasts, 1 errors, publish=True | RuntimeError x1: boom")
        self.assertEqual(cfg.run_summary("refresh", [], False), "MV2 forecast run (refresh): 0 forecasts, 0 errors, publish=False")

    def test_summary_reports_research_fallbacks(self):
        line = cfg.run_summary("test", [object()], True, research_fallbacks=2)
        self.assertEqual(line, "MV2 forecast run (test): 1 forecasts, 0 errors, publish=True | research_fallbacks=2")


if __name__ == "__main__":
    unittest.main()
