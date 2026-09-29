"""Bazaraki connector: page data decoding and parsing, from trimmed saved pages, without network."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from server import bazaraki

PAGES = Path(__file__).parent / "fixtures" / "bazaraki"
AREAS = {
    "Panthea": {"coords": [34.7003, 33.0539]},
    "Neapolis": {"coords": [34.6931, 33.0399]},
    "Kato Polemidia": {"coords": [34.6932, 32.9998]},
    "Agios Spyridon": {"coords": [34.6878, 33.0453]},
}


def page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


def offline(url: str) -> str:
    """Stand-in for `_get`: serves the fixture for each URL the connector may request."""
    path = url.removeprefix(bazaraki.BASE)
    if path.startswith("/map/"):
        return page("map.html")
    if path.startswith(bazaraki.CATEGORY):
        return page("search.html")
    if path.startswith("/adv/"):
        return page("advert.html")
    raise AssertionError(f"unexpected request: {url}")


class Flight(TestCase):
    def test_chunks_are_joined_and_unescaped(self):
        text = bazaraki.flight(page("search.html"))
        self.assertEqual(bazaraki._value(text, "total_pages"), 30)
        self.assertEqual(bazaraki._value(text, "count"), 1754)
        adverts = bazaraki._value(text, "adverts")
        self.assertEqual(len(adverts), 5)
        # The advert list straddles the two push chunks; decoding restores it whole.
        self.assertEqual(adverts[0]["location"], "Limassol — Panthea")
        self.assertIsNone(bazaraki._value(text, "no_such_key"))

    def test_page_without_data_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "no page data"):
            bazaraki.flight("<html><body>Checking your browser</body></html>")


class Fields(TestCase):
    def test_bedrooms(self):
        self.assertEqual(bazaraki.bedrooms_of("2-bedroom apartment to rent"), 2)
        self.assertEqual(bazaraki.bedrooms_of("Studio to rent"), 0)
        self.assertEqual(bazaraki.bedrooms_of("5 and more"), 5)
        self.assertEqual(bazaraki.bedrooms_of(" 3 "), 3)
        self.assertIsNone(bazaraki.bedrooms_of("Apartment to rent"))

    def test_area(self):
        self.assertEqual(bazaraki.area_of("Limassol — Limassol - Agia Zoni"), ("Limassol", "Agia Zoni"))
        self.assertEqual(bazaraki.area_of("Limassol — Panthea"), ("Limassol", "Panthea"))
        self.assertEqual(bazaraki.area_of(""), ("Limassol", ""))

    def test_offer_from_search_card(self):
        raw = bazaraki._value(bazaraki.flight(page("search.html")), "adverts")[0]
        offer = bazaraki._offer(raw, AREAS)
        self.assertEqual(offer["id"], "6701616")
        self.assertEqual(offer["url"], "https://www.bazaraki.com/adv/6701616_2-bedroom-apartment-to-rent/")
        self.assertEqual(offer["price"], 1600.0)
        self.assertEqual(offer["bedrooms"], 2)
        self.assertEqual(offer["size"], 88.0)
        self.assertEqual((offer["city"], offer["area"]), ("Limassol", "Panthea"))
        self.assertEqual(offer["coords"], AREAS["Panthea"]["coords"])
        self.assertEqual(offer["coord_kind"], "area")
        self.assertTrue(offer["thumb"].startswith("https://cdn1.bazaraki.com/"))
        self.assertNotIn("user", offer)

    def test_offer_outside_known_areas_and_non_advert_links(self):
        raw = bazaraki._value(bazaraki.flight(page("search.html")), "adverts")[4]
        offer = bazaraki._offer(raw, AREAS)
        self.assertEqual(offer["area"], "Limnatis")
        self.assertIsNone(offer["coords"])
        self.assertEqual(offer["coord_kind"], "unknown")
        self.assertIsNone(bazaraki._offer({"id": 1, "url": "/promo/top-offers/"}, AREAS))
        self.assertIsNone(bazaraki._offer({"id": 1, "url": "https://example.com/adv/1_x/"}, AREAS))


class Market(TestCase):
    def setUp(self):
        bazaraki._cache.clear()
        self.addCleanup(bazaraki._cache.clear)

    def test_snapshot_filters_and_places_offers(self):
        requested = []

        def get(url):
            requested.append(url)
            return offline(url)

        with patch.object(bazaraki, "_get", get), patch.object(bazaraki, "_areas", lambda: AREAS):
            result = bazaraki.market(1700, 2, pages=1)
            again = bazaraki.market(1700, 2, pages=1)
        self.assertIs(again, result)  # cached: no second read of the site
        self.assertEqual(requested, [
            "https://www.bazaraki.com/real-estate-to-rent/apartments-flats/lemesos-district-limassol/?price_max=1700",
            "https://www.bazaraki.com/map/real-estate-to-rent/apartments-flats/lemesos-district-limassol/?price_max=1700",
        ])
        self.assertTrue(all("/api" not in u and "attrs_" not in u for u in requested))
        self.assertEqual((result["listed"], result["total_pages"], result["scanned"]), (1754, 30, 5))
        # Three map points belong to scanned offers (one placed automatically); the fourth is not in the search.
        self.assertEqual(result["exact_coords"], 3)
        offers = {o["id"]: o for o in result["offers"]}
        # €1,900 is over the ceiling; the 1-bedroom offers are under the bedroom minimum.
        self.assertEqual(sorted(offers), ["6643257", "6701616"])
        self.assertEqual(offers["6701616"]["coord_kind"], "source")
        self.assertAlmostEqual(offers["6701616"]["coords"][0], 34.70, places=1)
        self.assertEqual(offers["6643257"]["coord_kind"], "unknown")

    def test_auto_placed_map_points_count_as_area(self):
        with patch.object(bazaraki, "_get", offline), patch.object(bazaraki, "_areas", lambda: AREAS):
            result = bazaraki.market(2000, 1, pages=1)
        offers = {o["id"]: o for o in result["offers"]}
        self.assertEqual(offers["6639339"]["coord_kind"], "area")
        self.assertEqual(offers["6623343"]["coord_kind"], "source")
        self.assertEqual(offers["6737448"]["coords"], AREAS["Agios Spyridon"]["coords"])


class Advert(TestCase):
    def test_advert_page_becomes_an_import_item(self):
        requested = []

        def get(url):
            requested.append(url)
            return offline(url)

        with patch.object(bazaraki, "_get", get):
            item = bazaraki.advert("https://www.bazaraki.com/adv/6359267_1-bedroom-apartment-to-rent/?utm=x")
        self.assertEqual(requested, ["https://www.bazaraki.com/adv/6359267_1-bedroom-apartment-to-rent/"])
        self.assertEqual(item["url"], "https://www.bazaraki.com/adv/6359267_1-bedroom-apartment-to-rent/")
        self.assertEqual(item["title"], "1-bedroom apartment to rent")
        self.assertEqual(item["price"], 1350.0)
        self.assertEqual(item["bedrooms"], 1)
        self.assertEqual(item["size"], 50.0)
        self.assertEqual((item["city"], item["area"]), ("Limassol", "Zakaki"))
        self.assertTrue(item["furnished"])
        self.assertTrue(item["balcony"])
        self.assertEqual(item["parking"], "unknown")
        self.assertTrue(item["available"])
        self.assertEqual(len(item["photo_urls"]), 3)
        self.assertEqual(item["coord_kind"], "source")
        self.assertAlmostEqual(item["coords"][1], 32.996, places=3)
        self.assertNotIn("seller", str(item))

    def test_only_advert_urls_are_read(self):
        with patch.object(bazaraki, "_get", lambda url: self.fail(f"requested {url}")):
            for url in ("https://www.bazaraki.com/real-estate-to-rent/", "https://example.com/adv/1_x/",
                        "https://www.bazaraki.com/api/items/1/"):
                with self.assertRaises(ValueError):
                    bazaraki.advert(url)

    def test_removed_advert_is_reported(self):
        with patch.object(bazaraki, "_get", lambda url: page("search.html")):
            with self.assertRaisesRegex(ValueError, "removed"):
                bazaraki.advert("https://www.bazaraki.com/adv/1_gone/")
