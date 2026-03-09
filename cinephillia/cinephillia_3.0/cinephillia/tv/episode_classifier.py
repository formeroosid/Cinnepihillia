import logging
from cinephillia.core.media_analyzer import detect_resolution, get_duration

log = logging.getLogger(__name__)


def classify_titles(titles, episode_duration_range=(2400, 3200)):
    """
    Split parsed titles into episodes vs extras based on duration.
    Attaches media_info dict to each title.
    """
    lo, hi = episode_duration_range
    episodes = []
    extras = []

    for t in titles:
        path_str = str(t["path"])
        duration = get_duration(path_str)
        width, height = detect_resolution(path_str)
        media_info = {
            "duration_seconds": duration,
            "width": width,
            "height": height,
        }
        enriched = {**t, "media_info": media_info}

        if lo <= duration <= hi:
            episodes.append(enriched)
        else:
            extras.append(enriched)
            log.info(f"Classified as extra ({duration:.0f}s): {t['path'].name}")

    log.info(f"Classified {len(episodes)} episodes, {len(extras)} extras")
    return episodes, extras
