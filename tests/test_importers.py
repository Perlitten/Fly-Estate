"""Catalogue photo identity and download outcome tests."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from PIL import Image

from server import importers


class Photos(TestCase):
    def test_identical_images_share_a_file_and_keep_url_outcomes(self):
        output = BytesIO()
        Image.new("RGB", (12, 12), "red").save(output, "PNG")
        blob = output.getvalue()
        urls = ["https://example.com/one", "https://example.com/two", "https://example.com/missing"]

        def fetch(url, hosts, limit):
            if url == urls[2]:
                raise ValueError("Blocked by source")
            return blob

        with TemporaryDirectory() as folder, patch.object(importers, "ROOT", Path(folder)), patch.object(importers, "fetch", fetch):
            listing = {"photo_urls": urls, "photos": []}
            warnings = importers.photos(listing)
            self.assertEqual(len(listing["photos"]), 1)
            self.assertEqual(len(listing["photo_downloads"]), 3)
            self.assertEqual([x["status"] for x in listing["photo_downloads"]],
                             ["available", "available", "unavailable"])
            self.assertEqual(listing["photo_downloads"][0]["path"], listing["photo_downloads"][1]["path"])
            self.assertIn(urls[2], warnings[0])

    def test_reimport_keeps_prior_photo_when_source_fails(self):
        output = BytesIO()
        Image.new("RGB", (12, 12), "blue").save(output, "PNG")
        url = "https://example.com/one"
        with TemporaryDirectory() as folder, patch.object(importers, "ROOT", Path(folder)):
            with patch.object(importers, "fetch", return_value=output.getvalue()):
                previous = {"photo_urls": [url], "photos": []}
                importers.photos(previous)
            with patch.object(importers, "fetch", side_effect=ValueError("Blocked by source")):
                listing = {"photo_urls": [url], "photos": []}
                importers.photos(listing, previous=previous)
            self.assertEqual(listing["photos"], previous["photos"])
            self.assertEqual(listing["photo_downloads"][0]["status"], "cached")
