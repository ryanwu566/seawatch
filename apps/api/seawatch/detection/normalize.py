"""Per-region feature normalisation: express every feature as 'how unusual for THIS region'.

Raw units differ between coasts (typical speeds, reporting rates, vessel mix). Mapping each
feature to its empirical percentile within the region's own historic windows removes that
shift, so a model learned on San Francisco Bay can be applied to Taiwan waters.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class RegionNormalizer:
    def __init__(self, features: list[str]):
        self.features = list(features)
        self.ref: dict[str, np.ndarray] = {}

    def fit(self, history: pd.DataFrame) -> "RegionNormalizer":
        for f in self.features:
            self.ref[f] = np.sort(history[f].to_numpy(float))
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for f in self.features:
            ref = self.ref[f]
            v = df[f].to_numpy(float)
            lo = np.searchsorted(ref, v, side="left")
            hi = np.searchsorted(ref, v, side="right")
            out[f] = (lo + hi) / (2.0 * len(ref))  # mid-rank percentile, ties handled
        return out
