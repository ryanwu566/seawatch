# Bundled emergency geography

`taiwan-emergency.geojson` is a deliberately simplified Taiwan/Penghu outline
derived from Natural Earth public-domain geography. It is bundled into the web
build and provides orientation only when both NLSC and the operator-installed
PMTiles archive are unavailable. It contains no live, military, or sensitive
location data.

The operational PMTiles archive is intentionally not committed. Install it at
the runtime path documented in `docs/offline-map.md` and set
`SEAWATCH_PMTILES_FILE`; the browser always requests
`/offline/taiwan.pmtiles` from its current FastAPI origin.
