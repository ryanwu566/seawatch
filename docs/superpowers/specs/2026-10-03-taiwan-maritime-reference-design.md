# Taiwan Maritime Reference Data Design

## Intent and scope

Build a reproducible, reference-only data pipeline for the Taiwan-area maritime geography used by future SeaWatch map and detection work. The pipeline owns acquisition, transformation, validation, deterministic serialization, provenance, and checked-in AOI artifacts. It does not alter any runtime API, live AIS, detection, authentication, or frontend behavior.

The area of interest (AOI) is longitude 115–126 E and latitude 20–27 N. All outputs are RFC 7946 GeoJSON coordinates in WGS84 (EPSG:4326).

## Source selection

### EEZ reference areas

Use the Marine Regions / Flanders Marine Institute WFS `eez` feature type, queried with the AOI bbox. The selected release is World EEZ v12, dated 2023-10-25. Retain all useful WFS identifiers and claimant fields, including overlapping Taiwan/China and Senkaku Islands Taiwan/Japan/China features. Clip features independently and never dissolve or select a preferred claimant.

### Official outer-limit lines

Use the Taiwan Ministry of the Interior Department of Land Administration open-data ZIP resources for:

- `中華民國12浬領海外界線` (`10906我國12浬領海外界線_98年修正`)
- `中華民國24浬鄰接區外界線` (`10906中華民國24浬鄰接區外界線`)

The archives contain PolyLine shapefiles without `.prj` files. Their official TGOS metadata identifies the CRS as EPSG:4326, and their numeric coordinate ranges agree with geographic WGS84. Read their UTF-8 DBF `Region` values, preserve source record identity, and clip the linework to the AOI. These outputs are published source lines, not polygons.

## Derived geometry decision

The inspected MOI line parts are closed, simple rings. Shapely polygonization yields one valid polygon per closed part, with no dangles, cut edges, or invalid remnants. The three 24 NM AOI polygons cover their region-matched 12 NM polygons, and their differences are valid. Therefore the pipeline will generate:

- `territorial_sea_12nm_reference_polygon.geojson` by strict polygonization of the MOI 12 NM closed line parts; and
- `contiguous_zone_12_24nm_reference_band.geojson` by subtracting each region-matched derived 12 NM polygon from its derived 24 NM polygon.

Both layers are SeaWatch `derived_reference` geometry. They are not described as official government polygons. Polygonization must fail closed if source parts cease to be closed/simple, polygonize ambiguously, or the 24 NM geometry no longer covers its matching 12 NM geometry.

## Pipeline architecture

`scripts/build_taiwan_maritime_reference.py` has two boundaries:

1. Acquisition downloads the AOI-limited Marine Regions GeoJSON and the two small MOI ZIPs into an overridable cache directory. The default cache is under the operating-system temporary directory, outside Git artifacts. Existing cached inputs are reused unless refresh is requested.
2. Transformation consumes local source paths, validates their schemas/geometries/CRS, clips each feature independently, derives polygons only through the strict checks above, validates final geometry, applies stable feature and geometry ordering, and writes canonical UTF-8 JSON atomically.

For the stable MOI ZIP resources, the script computes SHA-256 values over the exact retrieved bytes. The live WFS response contains volatile response-envelope metadata, including a retrieval timestamp, so the script instead computes a canonical semantic SHA-256 over the complete, deterministically ordered feature content and CRS. It excludes volatile top-level response metadata, intentionally omits the raw WFS hash from deterministic checked-in metadata, and fails closed unless the result matches the reviewed World EEZ v12 AOI snapshot pin. Metadata labels all checksums as pipeline-computed, not publisher-supplied. A caller-supplied retrieval date makes test and archival builds explicit; it does not affect GeoJSON geometry ordering.

The only added dependency is `pyshp`, recorded in a script-specific requirements file. Existing pinned Shapely and PyProj are reused. GeoPandas/GDAL are not added.

## Output contract

The output directory contains:

- `eez_reference_areas.geojson`
- `territorial_sea_12nm_official_line.geojson`
- `contiguous_zone_24nm_official_line.geojson`
- `territorial_sea_12nm_reference_polygon.geojson`
- `contiguous_zone_12_24nm_reference_band.geojson`
- `source_metadata.json`
- `README.md`

Source geometries use `geometry_status: "clipped_source"`; derived polygons and bands use `geometry_status: "derived_reference"`. Every collection and feature carries the legal and navigation caveats. Official line files contain only line geometry. Derived files contain only polygonal geometry.

GeoJSON feature order is stable by source identifier/region, properties are key-sorted, geometries are normalized, coordinates are serialized at fixed precision, and JSON formatting is stable. MultiPolygons and interior rings remain intact. Geometry repair is allowed only after a source validity failure, uses Shapely `make_valid`, and is recorded per feature and in output metadata.

## Metadata and documentation

`source_metadata.json` contains one record per generated GeoJSON output with all fields requested in the task, plus checksum provenance, WFS version-pin validation, direct license URLs, and any source-date notes. Full-source EEZ area/centroid attributes are qualified with `source_` names so they cannot be mistaken for clipped-geometry measurements. The README documents sources, URLs, versions, licenses, attribution, CRS, AOI, rebuild commands, the source/derived distinction, disputed-claim handling, and future-only MapLibre/detection integration guidance.

Every layer and the README state:

> Reference only. Not an adjudication of maritime sovereignty, jurisdiction, or legal boundaries.

They also state that the data is not for navigation, overlapping claims are preserved, no claimant is legally preferred, and source boundaries retain provenance.

## Validation and testing

Network acquisition is kept out of deterministic tests. Focused pytest tests build small local source fixtures with the real source schemas and exercise the local transformation boundary. They verify CRS metadata, GeoJSON validity, AOI bounds, non-empty/valid geometries, deterministic ordering/bytes, complete per-output metadata, source-versus-derived labels and geometry types, overlapping EEZ preservation, both caveats, licenses/source identity, reproducible clipping, and absence of global artifacts in the Git data directory.

The generated production artifacts receive a committed read-only contract test and an additional validation pass with the same invariants, file-size inspection, and feature-count reporting.

## Limitations

- Marine Regions WFS is a live service even though this build targets v12. Timestamp-only response changes are ignored semantically, while changed feature content fails the pinned AOI semantic checksum and requires explicit review before the pin is updated.
- The MOI archives omit `.prj`; EPSG:4326 comes from the corresponding official TGOS metadata rather than an embedded shapefile projection file.
- MOI source-date metadata and archive naming are not fully aligned, so both are recorded rather than silently reconciled.
- The derived polygons/band are visualization and lookup references only and have no official or navigational status.
- Canonical GeoJSON retains reviewed source detail. Any future simplified `*_display.geojson` layer must be a separately named derived product with documented tolerance and topology validation.
