# Release process

The release script promotes one Ground Station version through Gitea, Drone,
GHCR, and GitHub. It owns the version change and README changelog update, creates
one annotated tag, and pushes only that tag.

## Before starting

Run the script from a clean `main` branch after the current branch has been
pushed to both `origin/main` and `github/main`. The current commit must have a
successful GitHub `Tests` workflow run.

Do not edit `backend/server/version.json` before running the script. Pass the
new version on the command line; the script updates and commits it together with
the new README Recent Releases entry. The changelog is trimmed to the newest 10
entries before the release tag is created.

The required local commands are `python3`, `git`, `gh`, and `docker`. The GitHub
CLI must be authenticated, and the Docker CLI must be able to inspect the public
GHCR images.

## Inspect available options

```bash
./scripts/release.py --help
```

## Dry run with inline notes

Dry run is the default. It performs the preflight checks and previews the README
entry without committing, tagging, pushing, or starting Drone:

```bash
./scripts/release.py 0.8.12 \
  --notes "Added automated release validation; improved multi-architecture image checks; and fixed accidental tag publication."
```

Representative output:

```text
[release] GitHub Tests passed for ab12cd34 (...)
[release] Current version: 0.8.11; target: 0.8.12; tag: v0.8.12
[release] README entry: v0.8.12 (2026-09-18): Added automated release validation; ...
[release] README will remove: * **v0.7.19 (2026-08-01)
[release] Dry run passed. No commit, tag, image, release, or remote ref was changed.
```

## Execute the release

After reviewing the dry-run output, repeat the same command with `--execute`:

```bash
./scripts/release.py 0.8.12 \
  --notes "Added automated release validation; improved multi-architecture image checks; and fixed accidental tag publication." \
  --execute
```

The script then:

1. Updates `backend/server/version.json` and the README changelog.
2. Commits both files and creates annotated tag `v0.8.12` at that commit.
3. Pushes `main` and only `v0.8.12` to `origin`, triggering Drone.
4. Waits for the AMD64, ARM64, and combined GHCR manifests.
5. Confirms the architecture-specific digests match the combined manifest.
6. Pushes `main` and only `v0.8.12` to `github`.
7. Waits for GitHub Actions to publish the release page.

## Read notes from a file

For longer summaries, put a single paragraph in a temporary file outside the
repository. For example, `/tmp/ground-station-v0.8.12.txt` could contain:

```text
Added automated release validation and resumable promotion; improved AMD64,
ARM64, and combined manifest verification; and fixed accidental publication of
unrelated local tags.
```

Use the same file for dry run and execution:

```bash
./scripts/release.py 0.8.12 \
  --notes-file /tmp/ground-station-v0.8.12.txt

./scripts/release.py 0.8.12 \
  --notes-file /tmp/ground-station-v0.8.12.txt \
  --execute
```

Line breaks in the file are collapsed into one changelog paragraph. A notes file
inside the repository makes the worktree dirty and is rejected.

## Set an explicit release date

The default is the computer's current local date. Override it when preparing a
release around midnight or resuming on another day:

```bash
./scripts/release.py 0.8.12 \
  --release-date 2026-09-18 \
  --notes-file /tmp/ground-station-v0.8.12.txt
```

Use the same `--release-date` value when executing the release.

## Resume an interrupted release

The process is resumable. If the terminal closes, Drone takes longer than the
configured timeout, or GitHub Actions is delayed, rerun the execution command
for the same version:

```bash
./scripts/release.py 0.8.12 --execute
```

Once the version and changelog commit exists, notes are no longer required.
Existing local and remote tags must still point to that commit. Completed stages
are validated and reused; tags are never moved or recreated at another commit.

Pressing `Ctrl+C` while waiting for Drone is safe. It stops only the local
script; it does not cancel Drone or remove completed images.

## Change waiting behavior

Drone/GHCR waits up to six hours by default, and GitHub Actions waits up to 15
minutes. The registry is checked every 30 seconds. For example:

```bash
./scripts/release.py 0.8.12 \
  --notes-file /tmp/ground-station-v0.8.12.txt \
  --image-timeout 14400 \
  --release-timeout 1200 \
  --poll-interval 60 \
  --execute
```

Timeouts do not roll back commits, tags, or images. Fix the reported problem and
rerun the same version to continue.

## Exceptional CI bypass

If GitHub Actions cannot be queried and the commit has been verified separately,
the pre-release CI check can be bypassed explicitly:

```bash
./scripts/release.py 0.8.12 \
  --notes-file /tmp/ground-station-v0.8.12.txt \
  --skip-ci-check
```

This option affects only the initial GitHub Tests check. All version, tag,
remote, changelog, and image checks still run.

## Common preflight failures

- **Dirty worktree:** Commit or remove local changes before releasing.
- **Branches differ:** Synchronize local `main`, `origin/main`, and
  `github/main`, then rerun.
- **Version already in use:** Choose a new version. The script will not overwrite
  an existing tag, image, or GitHub release.
- **Latest Tests run failed:** Fix the failure and obtain a successful run before
  releasing.
- **Image timeout:** Inspect the Drone tag pipeline, resolve the build problem,
  and rerun the same execution command.
