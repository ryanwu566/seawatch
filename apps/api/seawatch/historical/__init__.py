"""Historical AIS ingestion pipeline for SeaWatch.

Pipeline flow:
    AIS raw data (any source)
    → HistoricalAisAdapter.load_tracks()   [adapter layer — swap here for NOAA]
    → historical/baseline.py               [trajectory building + baseline]
    → VesselBaseline                       [feeds route_deviation evidence]
    → Vessel Intelligence Card             [frontend consumption]

The adapter layer is the ONLY seam that changes when NOAA/NODASS data arrives.
Everything downstream is source-agnostic.
"""
