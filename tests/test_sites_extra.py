"""Site list additions and host matching."""
import unittest

from ytget_gui import sites


class SiteListTests(unittest.TestCase):
    def test_keys_and_domains_are_unique(self):
        keys = [key for key, _label, _domains in sites.SITES]
        self.assertEqual(len(keys), len(set(keys)))
        domains = [d for _k, _l, ds in sites.SITES for d in ds]
        self.assertEqual(len(domains), len(set(domains)))

    def test_every_entry_has_a_label_and_a_domain(self):
        for key, label, domains in sites.SITES:
            self.assertTrue(key and label and domains, key)

    def test_legacy_alias_still_points_at_the_list(self):
        self.assertIs(sites.POPULAR_SITES, sites.SITES)

    def test_default_enabled_keys_all_exist(self):
        known = {key for key, _l, _d in sites.SITES}
        for key in sites.DEFAULT_ENABLED_SITE_KEYS:
            self.assertIn(key, known)

    def test_adult_sites_are_not_enabled_by_default(self):
        for key in ("pornhub", "xvideos", "xhamster", "redtube"):
            self.assertNotIn(key, sites.DEFAULT_ENABLED_SITE_KEYS)


class NewSiteMatchingTests(unittest.TestCase):
    def test_added_sites_resolve(self):
        cases = {
            "https://www.pornhub.com/view_video.php?viewkey=abc": "pornhub",
            "https://store.steampowered.com/app/1/Foo/": "steam",
            "https://www.patreon.com/posts/123": "patreon",
            "https://t.me/somechannel/42": "telegram",
            "https://www.aparat.com/v/abc123": "aparat",
            "https://www.zdf.de/video/x": "zdf",
            "https://drive.google.com/file/d/abc/view": "googledrive",
        }
        for url, expected in cases.items():
            self.assertEqual(sites.site_key_for(url), expected, url)

    def test_a_lookalike_host_is_not_matched(self):
        self.assertEqual(
            sites.site_key_for("https://evil.example/?next=pornhub.com"), ""
        )

    def test_new_sites_follow_the_allowlist(self):
        self.assertFalse(sites.is_site_enabled("https://pornhub.com/x", []))
        self.assertTrue(
            sites.is_site_enabled("https://pornhub.com/x", ["pornhub"])
        )


if __name__ == "__main__":
    unittest.main()
