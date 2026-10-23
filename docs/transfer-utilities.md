# Standalone transfer utility CLI

All five scripts in `utils/` show full help and exit with status 2 when invoked without arguments. `-h` and `--help` exit 0. Help and argument validation run before host, mount, credential, or filesystem checks. Only `cp2tv.sh` and `cp2movie.sh` default to the current directory, and only when at least one option is given; the other three utilities never select a source implicitly.

## Export on Larry

Both exporters require SOURCE and DEST, for either one encode-project title or a collection root:

```bash
copy_plex_tv.sh -n --mount /mnt/mule "/mnt/bigbrother/TV/Star Trek - Strange New Worlds{tvdb-382389}" /mnt/mule/TV
copy_plex_movies.sh -n --mount /mnt/mule "/path/to/Movie (Year)" /mnt/mule/Movies
```

Remove `-n` only after reviewing the preview. `--name NAME` overrides the single-title destination folder. Exporters follow symlinks, exclude hidden entries, and require rsync 3.2.3+ for `--mkpath`. No destination deletion occurs.

## Deploy on Lumpy

`cp2tv.sh` and `cp2movie.sh` with no arguments print help and copy nothing. With any option (`-n`, `--name`, `--no-refresh`, `--mount`), the source defaults to the current directory unless `--source DIR` is supplied. The output always prints the resolved source and labels it `explicit` or `current directory`.

```bash
cd "/mnt/mule/TV/Star Trek - Strange New Worlds{tvdb-382389}"
cp2tv.sh -n --name "${PWD##*/}"               # preview one series
cp2tv.sh --name "${PWD##*/}" --no-refresh     # copy, skip Plex refresh
cp2tv.sh --source . --name "${PWD##*/}"       # copy and refresh Plex

cd /mnt/mule/Movies
cp2movie.sh -n                                # preview the whole collection
```

A plain live copy with refresh has no option of its own, so pass `--source .` to start it from the current directory.

Source guards:

| Condition | Implicit source | Explicit `--source` |
|---|---|---|
| `/` | Refused | Refused |
| `$HOME` | Refused | Allowed |
| A mount root, such as `/mnt/mule` | Refused | Allowed |
| A tree containing the running script, such as Mule's root when run as `/mnt/mule/cp2tv.sh` | Refused | Refused |
| No regular MKV files, encode-project markers, or MKV symlinks | Refused | Refused |

Destinations remain `/data/Media/TV Shows/` and `/data/Media/Movies/`. Existing differing files can be replaced, without backups. Destination-only files are not deleted. `-n` performs no copy or refresh and needs no token. Live refresh requires exported `PLEX_TOKEN`; use `--no-refresh` to skip it. The scripts do not filter out unrelated visible files within the chosen source.

## Repository bundle

```bash
refresh-repomix.sh --source "$HOME/Cinnephiilia"
```

The old implicit `REPO_DIR` environment/default source is no longer used. `--output FILE` overrides `OUTPUT_FILE` or `cinnephillia.md`; relative output paths are relative to the source checkout. This utility generates a bundle, not a media copy. Its existing repomix security-check setting is unchanged.

## Regression tests

```bash
python3 -m unittest discover -s tests -p test_utility_cli.py -v
```

The tests use temporary directories and mocked operational commands. They check syntax, no-argument help, explicit help, invalid/missing arguments, required sources for the exporters and repomix, the cp2 current-directory default, and the cp2 source guards without copying media or contacting Plex. They do not validate real transfers, ownership changes, or repomix output.
