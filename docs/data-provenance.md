# NOAA AIS Data Provenance

## Dataset

SeaWatch Phase 1 uses the official NOAA Office for Coastal Management / MarineCadastre experimental GeoParquet product, **Automatic Identification System broadcast point data for U.S. waters 2024**. Only the daily file for **2024-01-01** is acquired.

- Source artifact: <https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-01.parquet>
- Official product notes: <https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/data/ais-broadcast-points-2024-readme.md>
- Official repository license statement: <https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/LICENSE.md>
- Official disclaimer: <https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/DISCLAIMER.md>

The official product notes identify daily Apache Parquet files in Azure Blob Storage, GeoParquet 1.0.0, Snappy compression, Point geometry in WKB, WGS 84, UTC timestamps, and observations downsampled to the nearest whole minute. Those statements describe the product; the manifest records the schema, geometry metadata, CRS, row count, file size, and digest measured from the downloaded artifact.

The cited attribution is Martin, Daniel R., Jesse Brass, Matthew Dornback, and Jeremy Fontenault (2025), *Nationwide Automatic Identification System 2024*, NOAA Office for Coastal Management, with acknowledgement to the U.S. Coast Guard Navigation Center.

## License

The product notes state that the 2024 broadcast-point data are licensed under **CC0 1.0 Universal**. The repository license also states that all content uses the CC0 1.0 Universal public-domain dedication. SeaWatch records this as the observed license without extending that statement to unrelated datasets.

## Study Area and Selection

The Phase 1 engineering smoke area is an inclusive San Francisco Bay bounding box:

```text
west  = -122.55
south =   37.68
east  = -122.25
north =   37.90
```

This is a development and QA choice, not an official NOAA study region or an official challenge region. The smoke output further selects AIS vessel-type codes 70 through 79, conventionally used for cargo categories. Vessel type is self-reported AIS information and is not independently verified identity.

The measured 2024-01-01 smoke fixture contains 5,581 observations from 15 complete cargo-vessel tracks. All eligible tracks fit below the 50,000-observation ceiling; no track was truncated, randomly sampled, or excluded by that ceiling.

## Identifier Handling

Raw source vessel identifiers are used only transiently during ignored local processing to group observations. Public processed and preview artifacts use a deterministic dataset-scoped `track_id`. The surrogate is a display/privacy control, not anonymization: deterministic hashing does not prevent re-identification by enumeration.

## Limitations

- The source is historical U.S. AIS data. It does not demonstrate coverage, model performance, or operational suitability in Taiwan.
- AIS vessel type and other broadcast attributes are self-reported and may be incomplete, stale, or incorrect.
- The official product is downsampled to the nearest whole minute, so it does not retain every original broadcast.
- Observation gaps may result from reception coverage, equipment state, transmission conditions, data processing, or other benign causes.
- Missing AIS is not automatically suspicious behavior and is not labeled as such in this data layer.
- This phase performs integrity and provenance QA only. It does not label military activity, hostile intent, grey-zone behavior, or anomalies.
- Unusual motion values are retained when they otherwise pass structural validation; this phase does not remove them merely for looking atypical.
- No gap interpolation is performed.
- NOAA's repository disclaimer describes the material as an as-is scientific product and assigns responsibility for use to the user.
