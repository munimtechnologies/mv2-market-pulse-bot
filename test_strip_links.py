"""Tests for mv2_config.strip_links: forecast comments must reach Metaculus with no links in them."""

import unittest

import mv2_config as cfg


class StripLinksTest(unittest.TestCase):
    def test_markdown_link_keeps_its_text(self):
        text = "# Summary\nSee [Reuters story](https://www.reuters.com/markets/x) now."
        self.assertEqual(cfg.strip_links(text), "# Summary\nSee Reuters story now.")

    def test_bare_urls_become_site_names_and_keep_punctuation(self):
        text = "Source: https://www.sec.gov/cgi-bin/browse?x=1, and www.cboe.com/vix."
        self.assertEqual(cfg.strip_links(text), "Source: sec, and cboe.")

    def test_bare_domains_become_site_names(self):
        text = "per bloomberg.com and finance.yahoo.com/quote/NVDA"
        self.assertEqual(cfg.strip_links(text), "per bloomberg and yahoo")

    def test_angle_bracket_autolink(self):
        self.assertEqual(cfg.strip_links("<https://x.com/a> ok"), "x ok")

    def test_image_and_parenthesised_urls(self):
        text = "![chart](https://a.org/p_(x)) and [Wiki](https://en.wikipedia.org/wiki/Foo_(bar))"
        self.assertEqual(cfg.strip_links(text), "chart and Wiki")

    def test_plain_market_text_is_untouched(self):
        text = "# Forecast\nVIX 20.31; U.S. 10 Yr 4.10%; e.g. NQ − ES."
        self.assertEqual(cfg.strip_links(text), text)

    def test_no_link_survives_a_mixed_report(self):
        text = (
            "# Summary\n## Research\n1. [A](https://a.com/1) 2. https://b.org/x?y=(1) 3. www.c.net\n"
            "4. <http://d.io/z> 5. e.gov/path 6. [https://f.com](https://f.com)\n"
        )
        out = cfg.strip_links(text)
        self.assertTrue(out.startswith("# Summary"))
        for fragment in ("http", "www.", "](", ".com", ".org", ".net", ".io", ".gov"):
            self.assertNotIn(fragment, out)

    def test_site_name(self):
        self.assertEqual(cfg.site_name("https://www.sec.gov/x"), "sec")
        self.assertEqual(cfg.site_name("bbc.co.uk"), "bbc")
        self.assertEqual(cfg.site_name("x.com"), "x")


if __name__ == "__main__":
    unittest.main()
