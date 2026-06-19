#!/usr/bin/env python3
"""Download the small DROID subset with local filesystem-safe paths.

The raw DROID object names include episode directories such as
``Mon_Dec__4_15:44:25_2023``. Some storage CLI / filesystem combinations reject
those local paths. This script preserves the object tree but replaces ``:`` with
``-`` in local path components.

Example:
    uv run examples/droid/download_droid_subset.py --dst data/droid_subset
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess


DEFAULT_SOURCE = "gs://gresearch/robotics/droid_raw/1.0.1/IRIS/success/2023-12-04"
DEFAULT_ANNOTATIONS = "gs://gresearch/robotics/droid_raw/1.0.1/aggregated-annotations-030724.json"


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True)
    return result.stdout


def list_objects(source: str) -> list[str]:
    output = run(["gcloud", "storage", "ls", "--recursive", source])
    objects = []
    for line in output.splitlines():
        uri = line.strip()
        if not uri.startswith("gs://"):
            continue
        # `gcloud storage ls --recursive` emits directory headers like
        # `gs://bucket/prefix/:` and `gs://bucket/prefix/subdir/:`.
        if uri.endswith("/:"):
            continue
        if uri.endswith("/"):
            continue
        objects.append(uri)
    return objects


def local_path_for_object(uri: str, source: str, dst: Path) -> Path:
    rel = uri.removeprefix(source.rstrip("/") + "/")
    safe_rel = Path(*[part.replace(":", "-") for part in rel.split("/")])
    return dst / safe_rel


def copy_one(uri: str, source: str, dst: Path, *, dry_run: bool, overwrite: bool) -> Path:
    local_path = local_path_for_object(uri, source, dst)
    if dry_run:
        return local_path
    if local_path.exists() and not overwrite:
        return local_path
    local_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gcloud", "storage", "cp", uri, str(local_path)], check=True)
    return local_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=DEFAULT_SOURCE, help="GCS prefix to copy recursively.")
    parser.add_argument("--dst", type=Path, default=Path("data/droid_subset"), help="Local output directory.")
    parser.add_argument("--annotations-src", default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--overwrite", action="store_true", help="Redownload files that already exist locally.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    args.dst.mkdir(parents=True, exist_ok=True)
    objects = list_objects(args.src)
    print(f"Found {len(objects)} objects under {args.src}")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(copy_one, uri, args.src, args.dst, dry_run=args.dry_run, overwrite=args.overwrite)
            for uri in objects
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            local_path = future.result()
            print(f"[{index}/{len(futures)}] {local_path}")

    annotations_dst = args.dst / Path(args.annotations_src).name
    if args.dry_run:
        print(f"[annotations] {annotations_dst}")
    else:
        subprocess.run(["gcloud", "storage", "cp", args.annotations_src, str(annotations_dst)], check=True)
        print(f"[annotations] {annotations_dst}")


if __name__ == "__main__":
    main()
