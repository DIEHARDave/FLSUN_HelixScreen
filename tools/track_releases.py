#!/usr/bin/env python3
"""Pins the newest HelixScreen releases that include a FLSun T1 package.

Writes versions/stable (newest full release) and versions/beta (newest
release or beta). Run by .github/workflows/track-releases.yml; a change
becomes a commit, which Moonraker's update manager shows as an update.
Prints a commit message when something changed.
"""

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from flsun_helixscreen import UPSTREAM, PLATFORM, version_key  # noqa: E402

VERSIONS = os.path.join(os.path.dirname(__file__), "..", "versions")


def releases(repo, token):
    out, page = [], 1
    while page <= 5:
        req = urllib.request.Request(
            "https://api.github.com/repos/%s/releases?per_page=100&page=%d"
            % (repo, page),
            headers={"Accept": "application/vnd.github+json"})
        if token:
            req.add_header("Authorization", "Bearer " + token)
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.loads(resp.read().decode())
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def channel_of(tag):
    """stable, beta, or None for other prereleases (dev, rc...)."""
    key = version_key(tag)
    if key is None:
        return None
    pre = tag.split("-", 1)[1] if "-" in tag else None
    if pre is None:
        return "stable"
    return "beta" if pre.startswith("beta") else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default=PLATFORM,
                        help="package platform to look for (for testing)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    best = {"stable": None, "beta": None}
    for rel in releases(UPSTREAM, os.environ.get("GITHUB_TOKEN")):
        tag = rel.get("tag_name", "")
        if rel.get("draft"):
            continue
        asset = "helixscreen-%s-%s.tar.gz" % (args.platform, tag)
        if asset not in {a["name"] for a in rel.get("assets", [])}:
            continue
        chan = channel_of(tag)
        if chan == "stable" and rel.get("prerelease"):
            chan = "beta"
        channels = {"stable": ("stable", "beta"), "beta": ("beta",)}.get(chan,
                                                                         ())
        for c in channels:
            if best[c] is None or version_key(tag) > version_key(best[c]):
                best[c] = tag

    changes = []
    for c in ("stable", "beta"):
        path = os.path.join(VERSIONS, c)
        try:
            with open(path) as f:
                old = f.read().strip()
        except FileNotFoundError:
            old = ""
        new = best[c] or ""
        print("%s: %s -> %s" % (c, old or "-", new or "-"), file=sys.stderr)
        if new != old and new:
            changes.append((c, new))
            if not args.dry_run:
                with open(path, "w") as f:
                    f.write(new + "\n")
    if changes:
        tags = sorted({t for _, t in changes}, key=version_key)
        names = " and ".join(c for c, _ in changes)
        print("HelixScreen %s (%s)" % (", ".join(tags), names))


if __name__ == "__main__":
    main()
