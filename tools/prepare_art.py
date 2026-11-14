"""Build WebP delivery assets from archived PNGs (Pillow is a development tool only)."""

import argparse
import json
from pathlib import Path

from PIL import Image
from frontiers.media import image_path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "art-source"
STATIC = ROOT / "src" / "frontiers" / "static"


def prepare(import_png=False):
    SOURCE.mkdir(parents=True, exist_ok=True)
    sources = sorted((STATIC if import_png else SOURCE).rglob("*.png"))
    if not sources:
        raise SystemExit("No source PNGs found")
    entries = []
    for path in sources:
        # All outputs and archived originals must stay inside this repository.
        relative = Path(image_path(path.with_suffix(".webp").name))
        archive = (SOURCE / relative.relative_to("images").with_suffix(".png")).resolve()
        target = (STATIC / relative).resolve()
        assert archive.is_relative_to(SOURCE.resolve()) and target.is_relative_to(STATIC.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        if import_png and archive.exists():
            raise RuntimeError(f"Archive already exists: {archive}")
        with Image.open(path) as image:
            dimensions = image.size
            image.save(target, format="WEBP", quality=90, method=6)
        with Image.open(target) as result:
            result.load()
            assert result.size == dimensions and result.format == "WEBP", path.name
        entries.append({"file": target.relative_to(STATIC).as_posix(), "dimensions": list(dimensions),
                        "png_bytes": path.stat().st_size, "webp_bytes": target.stat().st_size})
    # Archive originals only after every converted image has decoded successfully.
    if import_png:
        for path in sources:
            archive = SOURCE / Path(image_path(path.name)).relative_to("images")
            archive.parent.mkdir(parents=True, exist_ok=True)
            path.rename(archive)
        # An incremental import must retain the size report for earlier artwork.
        entries = []
        for path in sorted(SOURCE.rglob("*.png")):
            target = STATIC / image_path(path.with_suffix(".webp").name)
            with Image.open(path) as image:
                dimensions = image.size
            entries.append({"file": target.relative_to(STATIC).as_posix(), "dimensions": list(dimensions),
                            "png_bytes": path.stat().st_size, "webp_bytes": target.stat().st_size})
    report = {"quality": 90, "method": 6, "pillow_version": Image.__version__,
              "png_bytes": sum(item["png_bytes"] for item in entries),
              "webp_bytes": sum(item["webp_bytes"] for item in entries), "files": entries}
    (ROOT / "docs" / "art-size-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "files"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-png", action="store_true", help="One-time migration: archive PNGs currently in static")
    prepare(parser.parse_args().import_png)
