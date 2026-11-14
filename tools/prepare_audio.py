"""Encode archived MP3s using the saved Opus preset and preserve supplied Oggs.

FFmpeg is needed only for this preparation step, never on the game server.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/audio-source"
TARGET = ROOT / "src/frontiers/static/audio"
SETTINGS = Path(__file__).with_name("audio-settings.json")


def prepare(ffmpeg, import_mp3=False):
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    SOURCE.mkdir(parents=True, exist_ok=True)
    TARGET.mkdir(parents=True, exist_ok=True)
    imported = sorted(TARGET.glob("*.mp3")) if import_mp3 else []
    for path in imported:
        archive = SOURCE / path.name
        assert path.resolve().is_relative_to(ROOT) and archive.resolve().is_relative_to(ROOT)
        if archive.exists():
            if archive.read_bytes() != path.read_bytes():
                raise RuntimeError(f"Different original already archived: {archive}")
        else:
            shutil.copyfile(path, archive)

    entries = []
    sources = sorted([*SOURCE.glob("*.mp3"), *SOURCE.glob("*.ogg")])
    if len({source.stem for source in sources}) != len(sources):
        raise RuntimeError("Multiple audio originals have the same output name")
    for source in sources:
        target = TARGET / (source.stem + ".ogg")
        assert source.resolve().is_relative_to(ROOT) and target.resolve().is_relative_to(ROOT)
        bitrate = settings["bitrate_overrides_kbps"].get(source.stem, settings["bitrate_kbps"])
        vbr = settings.get("vbr_overrides", {}).get(source.stem, settings["vbr"])
        encoded = source.suffix == ".mp3"
        if encoded:
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                            "-map", "0:a:0", "-map_metadata", "-1", "-c:a", settings["codec"],
                            "-b:a", f"{bitrate}k", "-vbr", vbr,
                            "-compression_level", str(settings["compression_level"]),
                            "-application", settings["application"], "-ar", str(settings["sample_rate"]),
                            str(target)], check=True)
        else:
            shutil.copyfile(source, target)
        # Decode the complete output before removing any delivery MP3s.
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(target),
                        "-f", "null", "-"], check=True)
        if encoded and target.stat().st_size >= source.stat().st_size:
            raise RuntimeError(f"Encoding did not reduce {source.name}; keep the original and adjust the preset")
        entries.append({"file": target.name, "mode": "encoded" if encoded else "copied",
                        "bitrate_kbps": bitrate if encoded else None, "vbr": vbr if encoded else None,
                        "source_bytes": source.stat().st_size, "delivery_bytes": target.stat().st_size,
                        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    if not entries:
        raise RuntimeError("No audio originals found")
    report = {"preset": settings, "source_bytes": sum(e["source_bytes"] for e in entries),
              "delivery_bytes": sum(e["delivery_bytes"] for e in entries), "files": entries}
    (ROOT / "docs/audio-size-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for path in imported:
        assert path.resolve().parent == TARGET.resolve()
        assert (SOURCE / path.name).read_bytes() == path.read_bytes()
        path.unlink()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"), help="Path to FFmpeg")
    parser.add_argument("--import-mp3", action="store_true", help="Archive existing delivery MP3s before encoding")
    args = parser.parse_args()
    if not args.ffmpeg:
        parser.error("Install FFmpeg or specify --ffmpeg")
    prepare(args.ffmpeg, args.import_mp3)
