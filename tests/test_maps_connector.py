from __future__ import annotations

import unittest
from unittest.mock import patch

from Backend.MapsConnector import (
    MapsConnectorError,
    _destination_with_fallback,
    get_directions,
    search_places,
)


class MapsConnectorTests(unittest.TestCase):
    def test_missing_key_is_actionable(self) -> None:
        with patch("Backend.MapsConnector.get_config", return_value=""):
            with self.assertRaisesRegex(MapsConnectorError, "GEOAPIFY_API_KEY"):
                search_places("restaurants", latitude=28.6139, longitude=77.2090)

    @patch("Backend.MapsConnector._get")
    def test_restaurant_results_are_normalized(self, get_request) -> None:
        get_request.return_value = {
            "features": [{
                "geometry": {"coordinates": [77.2, 28.6]},
                "properties": {
                    "name": "Example Restaurant",
                    "formatted": "Example Road, Delhi",
                    "distance": 240,
                    "categories": ["catering.restaurant"],
                },
            }],
        }
        result = search_places("restaurants", latitude=28.6139, longitude=77.2090)
        self.assertTrue(result["ok"])
        self.assertEqual(result["category"], "catering.restaurant")
        self.assertEqual(result["places"][0]["name"], "Example Restaurant")
        self.assertEqual(result["places"][0]["distance_meters"], 240)
        self.assertIn("200000", get_request.call_args.args[1]["filter"])

    @patch("Backend.MapsConnector.geocode")
    def test_destination_retries_globally_after_empty_local_result(self, geocode) -> None:
        expected = {
            "formatted": "Yelahanka Railway Station, Bengaluru",
            "latitude": 13.1007,
            "longitude": 77.5963,
        }
        geocode.side_effect = [
            {"places": []},
            {"places": [expected]},
        ]
        place, scope = _destination_with_fallback(
            "Yehlanka Railway Station", 13.0894, 77.6315
        )
        self.assertEqual(scope, "global")
        self.assertEqual(place, expected)
        self.assertEqual(geocode.call_count, 2)
        self.assertEqual(geocode.call_args_list[0].args[1], 5)
        self.assertEqual(geocode.call_args_list[1].args, ("Yehlanka Railway Station", 5))

    @patch("Backend.MapsConnector.geocode")
    @patch("Backend.MapsConnector._get")
    def test_directions_accept_browser_coordinates(self, get_request, geocode) -> None:
        geocode.return_value = {"places": [{
            "formatted": "Yelahanka Railway Station, Bengaluru",
            "latitude": 13.1007,
            "longitude": 77.5963,
        }]}
        get_request.return_value = {"features": [{"properties": {
            "distance": 3400,
            "time": 620,
            "legs": [],
        }}]}
        result = get_directions(
            "",
            "Yelahanka Railway Station",
            origin_latitude=13.05,
            origin_longitude=77.60,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["origin"], "Current browser location")
        self.assertEqual(result["distance_meters"], 3400)


if __name__ == "__main__":
    unittest.main()
