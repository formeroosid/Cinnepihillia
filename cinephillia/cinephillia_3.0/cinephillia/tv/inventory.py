import subprocess
import re
import logging
from pathlib import Path
from collections import defaultdict

log = logging.getLogger(__name__)

FILEBOT_BIN = "filebot"


def fetch_tvdb_episodes(series_query, db="TheTVDB", order="Airdate"):
    """Fetch the full episode catalog from TVDB via FileBot -list."""
    cmd = [
        FILEBOT_BIN, "-list",
        "--db", db,
        "--order", order,
        "--q", series_query,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"FileBot -list failed: {result.stderr}")
        return []

    episodes = []
    for line in result.stdout.strip().splitlines():
        m = re.match(r".+ - (\d+)x(\d+) - (.+)", line)
        if m:
            episodes.append({
                "season": int(m.group(1)),
                "episode": int(m.group(2)),
                "title": m.group(3).strip(),
            })
    return episodes


def scan_plex_library(plex_series_root):
    """Scan existing Plex folder for S##E## files."""
    plex_series_root = Path(plex_series_root)
    found = []
    for season_dir in sorted(plex_series_root.iterdir()):
        if not season_dir.is_dir():
            continue
        for f in sorted(season_dir.glob("*.mkv")):
            m = re.search(r"S(\d+)E(\d+)", f.name)
            if m:
                found.append({
                    "season": int(m.group(1)),
                    "episode": int(m.group(2)),
                    "filename": f.name,
                })
    return found


def count_ripped_episodes(classified_episodes):
    """Count episode-length titles per season from disc rips."""
    counts = defaultdict(int)
    for ep in classified_episodes:
        counts[ep["season"]] += 1
    return dict(counts)


def inventory_report(series_query, ripped_episodes=None,
                     plex_series_root=None, db="TheTVDB"):
    """
    Compare TVDB catalog against ripped discs and/or Plex library.
    Returns dict with per-season stats and list of missing episodes.
    """
    tvdb_episodes = fetch_tvdb_episodes(series_query, db=db)
    if not tvdb_episodes:
        log.error("No episodes returned from TVDB.")
        return {}

    tvdb_by_season = defaultdict(list)
    for ep in tvdb_episodes:
        tvdb_by_season[ep["season"]].append(ep)

    have_set = set()
    if plex_series_root:
        plex_root = Path(plex_series_root)
        if plex_root.exists():
            plex_eps = scan_plex_library(plex_root)
            have_set = {(ep["season"], ep["episode"]) for ep in plex_eps}
    elif ripped_episodes:
        ripped_counts = count_ripped_episodes(ripped_episodes)
        for season, count in ripped_counts.items():
            for ep_num in range(1, count + 1):
                have_set.add((season, ep_num))

    report = {"seasons": {}, "missing": [], "summary": {}}
    total_tvdb = total_have = total_missing = 0

    for season in sorted(tvdb_by_season):
        season_eps = tvdb_by_season[season]
        s_have = [e for e in season_eps if (e["season"], e["episode"]) in have_set]
        s_miss = [e for e in season_eps if (e["season"], e["episode"]) not in have_set]

        report["seasons"][season] = {
            "tvdb_count": len(season_eps),
            "have_count": len(s_have),
            "missing_count": len(s_miss),
        }
        for ep in s_miss:
            report["missing"].append(ep)

        total_tvdb += len(season_eps)
        total_have += len(s_have)
        total_missing += len(s_miss)

    report["summary"] = {
        "series": series_query,
        "total_episodes": total_tvdb,
        "total_have": total_have,
        "total_missing": total_missing,
        "completion_pct": round(total_have / total_tvdb * 100, 1) if total_tvdb else 0,
    }
    return report


def print_inventory(report):
    s = report.get("summary", {})
    print(f"\n{'='*60}")
    print(f"  INVENTORY: {s.get('series', 'Unknown')}")
    print(f"  {s['total_have']}/{s['total_episodes']} episodes "
          f"({s['completion_pct']}% complete)")
    print(f"{'='*60}\n")

    for season, info in sorted(report.get("seasons", {}).items()):
        status = "✓" if info["missing_count"] == 0 else f"✗ missing {info['missing_count']}"
        print(f"  Season {season:2d}: {info['have_count']:3d}/{info['tvdb_count']:3d}  {status}")

    missing = report.get("missing", [])
    if missing:
        print(f"\n  MISSING EPISODES:")
        print(f"  {'-'*50}")
        for ep in missing:
            print(f"  S{ep['season']:02d}E{ep['episode']:02d} - {ep['title']}")
    else:
        print(f"\n  ✓ Collection is complete!")
    print()
