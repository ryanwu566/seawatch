# Offline map installation and behavior

SeaWatch uses a latched basemap hierarchy:

1. Online operation begins with the OpenFreeMap Liberty vector style in the
   existing MapLibre map. The NLSC orthophoto remains an alternate layer.
2. If the online style fails, or operation is explicitly offline, SeaWatch uses
   the local PMTiles archive.
3. Missing or failed PMTiles falls back to bundled emergency Taiwan/Penghu
   geography.

A failed source is not retried during the page session. Reload only after the
operator has corrected the source. Vessel, Area Scan geometry/results,
selected-track, commercial-port, and generic future overlays are reinstalled
after every style transition.

## Install an archive

Obtain or generate a legally redistributable Taiwan-area PMTiles v3 vector
archive before an outage. The current style expects OpenMapTiles-like source
layers named `water`, `landcover`, and `transportation`. The archive is an
operator artifact and must not be committed.

```powershell
$env:SEAWATCH_PMTILES_FILE = "D:\SeaWatch\maps\taiwan.pmtiles"
```

FastAPI exposes that exact configured regular file at the fixed same-origin URL
`/offline/taiwan.pmtiles`. GET and HEAD support standard single byte ranges.
Malformed, multiple, or unsatisfiable ranges return 416. Browser code has no
filesystem path or `VITE_*` archive setting, so relocating the file needs no web
rebuild.

Validate locally:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/offline/taiwan.pmtiles -Method Head
Invoke-WebRequest http://127.0.0.1:8000/offline/taiwan.pmtiles -Headers @{Range="bytes=0-15"}
```

Expected responses are 200 and 206 with `Accept-Ranges: bytes`. If the file is
absent, SeaWatch receives a local 404 and renders its bundled public-domain,
simplified Natural Earth geography. The emergency style contains no HTTP tile,
font, glyph, sprite, or CDN reference. It is orientation context, not a nautical
chart and not suitable for navigation.
