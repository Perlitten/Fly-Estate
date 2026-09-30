# Limassol highway position evidence

`highways-limassol.geojson` is a September 30, 2026 OpenStreetMap snapshot of the main A1/A6 carriageways around Limassol. © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright).

Sources: the public [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) and [OSM map API](https://wiki.openstreetmap.org/wiki/API_v0.6#Retrieving_map_data_by_bounding_box:_GET_/api/0.6/map).

The original motorway query covered latitude 34.63–34.77, longitude 32.85–33.20. Limassol's central A1 is tagged `trunk`; those sections were added from OSM map API bounding boxes (west, south, east, north):

- 33.025, 34.700, 33.050, 34.725
- 33.012, 34.690, 33.029, 34.715
- 33.050, 34.700, 33.073, 34.725
- 33.073, 34.700, 33.100, 34.727

Only ways with `ref=A1` or `ref=A6` and `highway=motorway` or `highway=trunk` were retained from these map responses, using their full ordered node coordinates. Features are deduplicated by OSM way ID. This snapshot is not automatically refreshed or fetched during startup.

The application projects an individual advert pin against these line segments for approximate distance and compares its latitude with the road crossing at the same longitude for side. Area-centre pins and missing longitudinal coverage return unknown. The nearest main carriageway distance is not a noise estimate; slip roads and actual address accuracy are not established. The source-pin rule is documented in [the teaching brief](../../docs/TEACHER_BRIEF.md).
