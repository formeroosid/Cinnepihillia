# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import logging

log = logging.getLogger(__name__)


def classify_titles(titles, duration_range):
    lo, hi = duration_range
    episodes = []
    extras = []

    for t in titles:
        duration = t.get("duration_minutes")

        # Skip titles with no duration; be conservative and treat as extra
        if duration is None:
            extras.append(t)
            continue

        if lo is not None and duration < lo:
            extras.append(t)
            continue

        if hi is not None and duration > hi:
            extras.append(t)
            continue

        episodes.append(t)

    log.info("Classified %d episodes, %d extras", len(episodes), len(extras))
    return episodes, extras