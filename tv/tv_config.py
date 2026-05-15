# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

"""
Per-series configuration overrides.
Duration ranges, FileBot hints, etc.
"""

SERIES_DEFAULTS = {
    "episode_duration_range": (2400, 3200),   # 40-53 min (drama)
    "db": "TheTVDB",
    "order": "DVD",
    "action": "duplicate",
}

# Override for specific series types
SERIES_OVERRIDES = {
    "sitcom": {
        "episode_duration_range": (1200, 1800),  # 20-30 min
    },
}
