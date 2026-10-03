# Taiwan Maritime Reference Data

These layers are reproducible maritime-reference geography for the SeaWatch Taiwan area of interest (AOI). They are prepared for future visualization and spatial lookup, not integrated into the application runtime on this branch.

> **Reference only. Not an adjudication of maritime sovereignty, jurisdiction, or legal boundaries.**

**Not for navigation.** Overlapping maritime claims are preserved as separate source features. SeaWatch does not select any claimant as legally preferred. Source boundaries are displayed with provenance.

## Coverage and coordinates

- AOI: longitude 115°E–126°E, latitude 20°N–27°N
- Output coordinates: WGS84 longitude/latitude, EPSG:4326
- Format: RFC 7946-style GeoJSON with SeaWatch foreign metadata members
- Coordinate precision: seven decimal places

## Layers

| File | Features | Status | Meaning |
|---|---:|---|---|
| `eez_reference_areas.geojson` | 5 | `clipped_source` | Marine Regions World EEZ v12 features intersecting the AOI, clipped independently. Includes separate Taiwan/China and Senkaku Islands Taiwan/Japan/China overlapping-claim features as supplied. |
| `territorial_sea_12nm_official_line.geojson` | 3 | `clipped_source` | Taiwan Ministry of the Interior (MOI) published 12 NM territorial-sea outer-limit **line** records in the AOI. This is not a polygon layer. |
| `contiguous_zone_24nm_official_line.geojson` | 3 | `clipped_source` | MOI published 24 NM contiguous-zone outer-limit **line** records in the AOI. This is not a polygon layer. |
| `territorial_sea_12nm_reference_polygon.geojson` | 3 | `derived_reference` | SeaWatch polygonization of closed, simple MOI 12 NM outer-limit line parts. This is a derived visualization/reference polygon, not an official MOI polygon. |
| `contiguous_zone_12_24nm_reference_band.geojson` | 3 | `derived_reference` | Region-matched derived 24 NM polygons minus matching derived 12 NM polygons. This is a SeaWatch reference band, not an official MOI polygon. |

`source_metadata.json` contains a provenance record for every GeoJSON output, including source organization, dataset and URL, release/date, retrieval date, license, build-computed source checksum, input/output CRS, AOI and clipping method, processing and derivation steps, geometry status, source/output feature counts, and caveats.

## Sources and licenses

### Marine Regions / VLIZ

- Dataset: **Maritime Boundaries and Exclusive Economic Zones (200NM), World EEZ v12**
- Release: **2023-10-25**
- AOI WFS request used by the build: <https://geo.vliz.be/geoserver/MarineRegions/wfs?service=WFS&version=1.0.0&request=GetFeature&typeName=eez&bbox=115,20,126,27&outputFormat=application/json&srsName=EPSG:4326>
- Product/download page: <https://www.marineregions.org/downloads.php>
- Citation: Flanders Marine Institute (2023), *Maritime Boundaries Geodatabase: Maritime Boundaries and Exclusive Economic Zones (200NM), version 12*, DOI <https://doi.org/10.14284/632>
- License: Creative Commons Attribution 4.0 International (CC BY 4.0), subject to the [Marine Regions license and terms of use](https://www.marineregions.org/disclaimer.php)
- Version validation: the build fails closed unless the AOI WFS feature semantics match the reviewed World EEZ v12 snapshot checksum recorded in the builder and metadata. A source change requires explicit review and a pin update.

Marine Regions states that its products have no legal value and are not intended for legal, economic-resource-exploration, or navigational purposes. This repository preserves that limitation.

The WFS bbox filter limits acquisition to features whose server-side envelopes intersect the AOI. Each returned geometry is then intersected with the AOI locally. One WFS feature with a broad envelope had an empty geometric intersection and was removed, producing 5 output features from 6 returned features. Features are never dissolved across claims.

### Taiwan Ministry of the Interior, Department of Land Administration

12 NM territorial-sea outer-limit line:

- Dataset page: <https://data.gov.tw/dataset/155452>
- Exact ZIP resource: <https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/DE466003-A5A6-442D-8C55-552A0451D0B5/resource/F78DBCE4-4CB3-42DA-8A8C-13281A1ECF51/download>
- Resource label/version: `10906我國12浬領海外界線_98年修正`; archive filename revision `ver1090623`
- Official TGOS source date: 2009-11-18

24 NM contiguous-zone outer-limit line:

- Dataset page: <https://data.gov.tw/dataset/163012>
- Exact ZIP resource: <https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/0B62D0ED-D732-4673-AA40-2724631BEFEC/resource/637A7B8A-0BB3-4662-9605-E747CCE05D78/download>
- Resource label/version: `10906中華民國24浬鄰接區外界線`; archive filename revision `ver1090623`
- Official TGOS source date: 2019-11-18

Both MOI resources use the **政府資料開放授權條款－第1版 (Open Government Data License, version 1.0)**, as recorded on their government data pages; the [official license text is published by data.gov.tw](https://data.gov.tw/license). They were retrieved on 2026-10-03.

The MOI ZIPs contain `.shp`, `.shx`, and `.dbf`, but no `.prj`. The corresponding official TGOS metadata identifies both resources as EPSG:4326; the source coordinate ranges also match geographic longitude/latitude. The `Region` DBF field is UTF-8. The 24 NM TGOS date and the `98年修正`/`ver1090623` naming are recorded independently because the publisher metadata does not explain their apparent date mismatch.

## Source lines versus derived references

The two `*_official_line.geojson` files preserve the MOI source geometry type. Their features use `geometry_status: "clipped_source"` because the build applies AOI selection/clipping.

The MOI line parts in this release are closed and simple. The builder requires `polygonize_full` to produce exactly one valid polygon per part with no dangles, cut edges, invalid remnants, nesting, or overlaps. If those checks fail in a later source, the build stops instead of fabricating a polygon.

The 12–24 NM band is constructed separately for each preserved `Region`. The builder requires every 24 NM AOI polygon to cover its matching 12 NM polygon before subtraction. Both derived files use `geometry_status: "derived_reference"`, carry the derivation method on every feature, and explicitly state that they are not official government polygons.

## Rebuild

Install the script-specific GIS dependencies in an appropriate Python environment:

```powershell
python -m pip install -r scripts/requirements-taiwan-maritime-reference.txt
```

Run the build from the repository root:

```powershell
python scripts/build_taiwan_maritime_reference.py `
  --output-dir data/gis/taiwan_maritime_reference `
  --retrieval-date 2026-10-03
```

By default, downloads are cached under the operating-system temporary directory, not in Git. Use `--cache-dir <path>` to choose another cache and `--refresh` to redownload. The Marine Regions request is AOI-limited; the two MOI archives are each under 0.5 MB. The builder validates all geometry and metadata before writing outputs and uses atomic replacement for each JSON file.

For deterministic local transformation tests (no network):

```powershell
python -m pytest tests/unit/test_taiwan_maritime_reference.py -q
```

## Determinism and validation

- Features sort by stable source identifiers/regions.
- Properties and JSON object keys are sorted.
- Geometry components/rings are normalized and coordinates use fixed precision.
- MultiPolygons, disjoint parts, and holes are retained.
- Every source and output geometry is checked for emptiness and validity.
- `make_valid` is used only if an EEZ source/clip is invalid, and any use is recorded. This retrieval required no repair.
- MOI SHA-256 values are computed by the SeaWatch build over the exact downloaded ZIP bytes and are marked as not publisher-supplied.
- The live WFS response includes a changing top-level retrieval timestamp. For that source, metadata records a canonical semantic SHA-256 over the complete, deterministically ordered feature content and CRS while excluding volatile response-envelope fields. The raw WFS hash is intentionally omitted from deterministic checked-in metadata. Timestamp-only responses therefore produce byte-identical outputs, while any feature-semantic change fails the pinned v12 snapshot check.
- Marine Regions attributes whose values describe the full source feature are explicitly qualified after AOI clipping: `source_area_km2`, `source_centroid_x`, and `source_centroid_y`. They must not be interpreted as measurements of the clipped output geometry.

## Disputed-boundary handling

EEZ features are clipped one at a time. The build does not union, dissolve, rank, or otherwise reconcile overlapping claims. Useful Marine Regions identifiers, territory fields, sovereign fields, and source names remain on the output features. This preserves the source's separate overlapping Taiwan/China and Senkaku Islands Taiwan/Japan/China records without adopting a political interpretation.

The MOI layers are presented with their publisher and derivation provenance. Their inclusion does not endorse or adjudicate any territorial or maritime claim.

## Future integration guidance (not implemented here)

MapLibre can load each file as a separate GeoJSON source. Render EEZ/reference polygons and bands as fill-plus-outline layers, and render official MOI limits as line layers. UI copy should display `geometry_status`, source attribution, and both caveats; derived fills must never be labeled as official boundaries.

The checked-in canonical files retain reviewed source detail and are not simplified. If map performance later requires it, create separately named, explicitly derived `*_display.geojson` products with documented tolerances and topology checks; do not replace or silently simplify the canonical reference artifacts.

A future detection/context service can perform territorial/EEZ reference lookup against these layers while returning all matching overlapping features. A lookup result is geographic context only—not a legality, sovereignty, authorization, or navigation decision.
