"""Read-only Geoapify connector used by Nexa's location tools."""

from __future__ import annotations

import logging
from typing import Any

import requests

from Backend.LLMProvider import get_config


class MapsConnectorError(RuntimeError):
    """A safe, user-actionable Geoapify connector error."""


GEOAPIFY_BASE_URL = "https://api.geoapify.com"
LOCAL_SEARCH_RADIUS_METERS = 200_000
logger = logging.getLogger("nexa.workflow.maps")


def geoapify_configured() -> bool:
    return bool(get_config("GEOAPIFY_API_KEY").strip())


def _api_key() -> str:
    value = get_config("GEOAPIFY_API_KEY").strip()
    if not value:
        raise MapsConnectorError(
            "Geoapify is not configured. Add GEOAPIFY_API_KEY to the project's .env file."
        )
    return value


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    request_params = {**params, "apiKey": _api_key()}
    # Deliberately log the exact request parameters for route debugging, while
    # excluding the API key. Coordinates are logged only in the local workflow
    # log because the user requested this diagnostic trace.
    logger.info("geoapify.request method=GET path=%s params=%s", path, params)
    try:
        response = requests.get(f"{GEOAPIFY_BASE_URL}{path}", params=request_params, timeout=25)
    except requests.RequestException as exc:
        raise MapsConnectorError("Geoapify could not be reached. Check the internet connection.") from exc
    logger.info("geoapify.response path=%s status=%d bytes=%d", path, response.status_code, len(response.content))
    if response.status_code in {401, 403}:
        raise MapsConnectorError("Geoapify rejected the API key. Check GEOAPIFY_API_KEY and its project permissions.")
    if response.status_code == 429:
        raise MapsConnectorError("Geoapify's request limit has been reached. Try again later.")
    if not response.ok:
        raise MapsConnectorError(f"Geoapify request failed ({response.status_code}).")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MapsConnectorError("Geoapify returned an invalid response.") from exc
    normalized = payload if isinstance(payload, dict) else {}
    logger.info(
        "geoapify.payload path=%s feature_count=%d top_level_keys=%s",
        path,
        len(normalized.get("features") or []),
        ",".join(str(key) for key in normalized.keys()),
    )
    return normalized


def _coordinates(latitude: float | None, longitude: float | None) -> tuple[float, float] | None:
    if latitude is None and longitude is None:
        return None
    if latitude is None or longitude is None:
        raise MapsConnectorError("Both latitude and longitude are required when using a current location.")
    lat, lon = float(latitude), float(longitude)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise MapsConnectorError("The supplied coordinates are outside the valid latitude/longitude range.")
    return lat, lon


def geocode(
    location: str,
    count: int = 5,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_meters: int | None = None,
) -> dict[str, Any]:
    text = " ".join(location.split())
    if not text:
        raise MapsConnectorError("A location, address, or place name is required.")
    params: dict[str, Any] = {"text": text, "limit": max(1, min(int(count), 10))}
    coordinates = _coordinates(latitude, longitude)
    scope = "global"
    if coordinates and radius_meters is not None:
        radius = max(100, min(int(radius_meters), LOCAL_SEARCH_RADIUS_METERS))
        lat, lon = coordinates
        params.update({
            "filter": f"circle:{lon},{lat},{radius}",
            "bias": f"proximity:{lon},{lat}",
        })
        scope = f"local_{radius}m"
    payload = _get("/v1/geocode/search", params)
    places = []
    for feature in payload.get("features") or []:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        coordinates = feature.get("geometry", {}).get("coordinates") or []
        if len(coordinates) < 2:
            continue
        places.append({
            "name": properties.get("name") or properties.get("formatted") or text,
            "formatted": properties.get("formatted") or "",
            "latitude": coordinates[1],
            "longitude": coordinates[0],
            "country": properties.get("country") or "",
            "city": properties.get("city") or properties.get("town") or properties.get("village") or "",
        })
    logger.info("geoapify.geocode scope=%s query=%r result_count=%d first_result=%s", scope, text, len(places), places[0] if places else None)
    return {"ok": True, "query": text, "scope": scope, "places": places, "result_count": len(places)}


def reverse_geocode(latitude: float, longitude: float) -> dict[str, Any]:
    """Resolve browser coordinates to a small, non-sensitive location record."""
    lat, lon = _coordinates(latitude, longitude) or (0.0, 0.0)
    payload = _get("/v1/geocode/reverse", {"lat": lat, "lon": lon, "limit": 1})
    features = payload.get("features") or []
    if not features or not isinstance(features[0], dict):
        raise MapsConnectorError("Geoapify could not determine the country for the supplied location.")
    properties = features[0].get("properties") or {}
    country_code = str(properties.get("country_code") or "").upper()
    if len(country_code) != 2:
        raise MapsConnectorError("Geoapify did not return a usable country code for the supplied location.")
    return {
        "country_code": country_code,
        "country": str(properties.get("country") or ""),
        "city": str(properties.get("city") or properties.get("town") or properties.get("village") or ""),
    }


def _destination_with_fallback(
    destination: str,
    latitude: float | None,
    longitude: float | None,
) -> tuple[dict[str, Any], str]:
    """Find a destination locally first, then retry globally only if needed."""
    coordinates = _coordinates(latitude, longitude)
    if coordinates:
        try:
            local = geocode(
                destination,
                5,
                coordinates[0],
                coordinates[1],
                LOCAL_SEARCH_RADIUS_METERS,
            )
            if local["places"]:
                logger.info("geoapify.destination scope=local_200km selected=%s", local["places"][0])
                return local["places"][0], "local_200km"
            logger.info("geoapify.destination scope=local_200km empty_result; retrying_global=true")
        except MapsConnectorError as exc:
            logger.warning("geoapify.destination scope=local_200km error=%s; retrying_global=true", exc)

    global_result = geocode(destination, 5)
    if not global_result["places"]:
        raise MapsConnectorError(f"Could not find the destination '{destination}'.")
    logger.info("geoapify.destination scope=global selected=%s", global_result["places"][0])
    return global_result["places"][0], "global"


def _resolve_origin(location: str, latitude: float | None, longitude: float | None) -> tuple[float, float, str]:
    coordinates = _coordinates(latitude, longitude)
    if coordinates:
        return coordinates[0], coordinates[1], "current browser location"
    result = geocode(location, 1)
    if not result["places"]:
        raise MapsConnectorError(f"Could not find the location '{location}'.")
    place = result["places"][0]
    return float(place["latitude"]), float(place["longitude"]), str(place["formatted"] or location)


def _place_categories(query: str) -> str:
    value = query.lower()
    mappings = (
        (("restaurant", "food", "dinner", "lunch", "breakfast", "eatery"), "catering.restaurant"),
        (("cafe", "coffee", "tea"), "catering.cafe"),
        (("bar", "pub", "nightclub"), "catering.bar"),
        (("hotel", "stay", "accommodation"), "accommodation.hotel"),
        (("hospital", "doctor", "clinic", "pharmacy"), "healthcare"),
        (("gas", "petrol", "fuel"), "service.vehicle.fuel"),
        (("atm",), "service.financial.atm"),
        (("bank",), "service.financial.bank"),
        (("parking",), "parking"),
        (("supermarket", "grocery"), "commercial.supermarket"),
        (("shopping", "mall", "store"), "commercial"),
        (("tourist", "attraction", "museum", "park", "landmark"), "tourism"),
    )
    for terms, category in mappings:
        if any(term in value for term in terms):
            return category
    return "commercial"


def search_places(
    query: str,
    location: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    radius_meters: int = LOCAL_SEARCH_RADIUS_METERS,
    count: int = 5,
) -> dict[str, Any]:
    cleaned_query = " ".join(query.split())
    if not cleaned_query:
        raise MapsConnectorError("Describe the type of place to find, for example 'restaurants' or 'coffee shops'.")
    lat, lon, origin = _resolve_origin(location, latitude, longitude)
    radius = max(100, min(int(radius_meters), LOCAL_SEARCH_RADIUS_METERS))
    local_params = {
        "categories": _place_categories(cleaned_query),
        "filter": f"circle:{lon},{lat},{radius}",
        "bias": f"proximity:{lon},{lat}",
        "limit": max(1, min(int(count), 10)),
    }
    scope = f"local_{radius}m"
    try:
        payload = _get("/v2/places", local_params)
        if not payload.get("features"):
            logger.info("geoapify.places scope=%s empty_result; retrying_global=true", scope)
            payload = _get("/v2/places", {
                "categories": _place_categories(cleaned_query),
                "limit": max(1, min(int(count), 10)),
            })
            scope = "global"
    except MapsConnectorError as exc:
        logger.warning("geoapify.places scope=%s error=%s; retrying_global=true", scope, exc)
        payload = _get("/v2/places", {
            "categories": _place_categories(cleaned_query),
            "limit": max(1, min(int(count), 10)),
        })
        scope = "global"
    places: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        places.append({
            "name": properties.get("name") or properties.get("address_line1") or "Unnamed place",
            "address": properties.get("formatted") or "",
            "latitude": coords[1] if len(coords) > 1 else None,
            "longitude": coords[0] if len(coords) > 1 else None,
            "distance_meters": properties.get("distance"),
            "categories": properties.get("categories") or [],
            "phone": properties.get("contact", {}).get("phone") if isinstance(properties.get("contact"), dict) else "",
            "website": properties.get("website") or "",
            "opening_hours": properties.get("opening_hours") or "",
        })
    return {
        "ok": True,
        "query": cleaned_query,
        "origin": origin,
        "scope": scope,
        "category": _place_categories(cleaned_query),
        "places": places,
        "result_count": len(places),
        "notice": "Geoapify place results do not include reliable venue photos or crowd ratings.",
    }


def get_directions(
    origin: str,
    destination: str,
    mode: str = "drive",
    origin_latitude: float | None = None,
    origin_longitude: float | None = None,
) -> dict[str, Any]:
    if mode not in {"drive", "walk", "bicycle"}:
        raise MapsConnectorError("Travel mode must be drive, walk, or bicycle.")
    browser_origin = _coordinates(origin_latitude, origin_longitude)
    start = [] if browser_origin else geocode(origin, 1).get("places", [])
    destination_center = browser_origin or (
        (float(start[0]["latitude"]), float(start[0]["longitude"])) if start else None
    )
    if not browser_origin and not start:
        raise MapsConnectorError("Could not find the origin for directions.")
    start_place = start[0] if start else {
        "latitude": browser_origin[0],
        "longitude": browser_origin[1],
        "formatted": "Current browser location",
    }
    end_place, destination_scope = _destination_with_fallback(
        destination,
        destination_center[0] if destination_center else None,
        destination_center[1] if destination_center else None,
    )
    logger.info(
        "geoapify.route.resolve origin=%s destination=%s mode=%s",
        start_place,
        end_place,
        mode,
    )
    route_params = {
        "waypoints": f"{start_place['latitude']},{start_place['longitude']}|{end_place['latitude']},{end_place['longitude']}",
        "mode": mode,
        "details": "instruction_details",
    }
    payload = _get("/v1/routing", route_params)
    features = payload.get("features") or []
    if not features and destination_scope == "local_200km":
        logger.info("geoapify.route scope=local_200km empty_result; retrying_global_destination=true")
        end_place, destination_scope = _destination_with_fallback(destination, None, None)
        route_params["waypoints"] = f"{start_place['latitude']},{start_place['longitude']}|{end_place['latitude']},{end_place['longitude']}"
        payload = _get("/v1/routing", route_params)
        features = payload.get("features") or []
    if not features:
        raise MapsConnectorError("Geoapify could not find a route for those locations.")
    properties = features[0].get("properties") or {}
    legs = properties.get("legs") or []
    steps = []
    for leg in legs:
        for step in leg.get("steps") or []:
            instruction = step.get("instruction") or {}
            text = instruction.get("text") if isinstance(instruction, dict) else ""
            if text:
                steps.append(text)
    return {
        "ok": True,
        "origin": start_place.get("formatted") or origin,
        "destination": end_place.get("formatted") or destination,
        "destination_scope": destination_scope,
        "mode": mode,
        "distance_meters": properties.get("distance"),
        "time_seconds": properties.get("time"),
        "steps": steps[:12],
    }
