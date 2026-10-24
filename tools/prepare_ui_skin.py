"""Stage reference artwork locally, without running the Windows application.

Vendor artwork is intentionally not included in the project's MIT-licensed
source. Supply an already-extracted skins directory, or a trusted innoextract
binary to statically unpack the repository's installer. Only allowlisted image
files and an optional font are copied to the ignored .work/ui-skin directory.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_SHA256 = "c45662764d9847e3b14c34d19a745e6b6b34a7e966889be18814cd5513c47468"
IMAGES = (
    "main_normal.jpg", "main_over.jpg", "main_down.jpg",
    "advanced_normal.jpg", "advanced_down.jpg",
    "mac_normal.jpg", "mac_down.jpg",
    "led_null.jpg", "led_normal.jpg", "led_down.jpg",
)
FONT = "config/font/Roboto-Regular.ttf"


def stage(source, destination):
    source, destination = Path(source), Path(destination)
    # Validate the complete source before creating any destination files.
    for name in IMAGES:
        path = source / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing regular reference image: {path}")
    if destination.exists():
        raise ValueError(f"Destination already exists; choose a new directory: {destination}")
    destination.mkdir(parents=True)
    hashes = {}
    names = list(IMAGES)
    if (source / FONT).is_file() and not (source / FONT).is_symlink():
        names.append(FONT)
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / "provenance.json").write_text(json.dumps({
        "purpose": "Local interoperability UI reference; not MIT-licensed project artwork",
        "installer_sha256": INSTALLER_SHA256,
        "files": hashes,
    }, indent=2) + "\n")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-directory", type=Path, help="already extracted app/skins directory")
    source.add_argument("--extractor", help="trusted innoextract binary (static extraction only)")
    parser.add_argument("--destination", type=Path, default=ROOT / ".work/ui-skin")
    args = parser.parse_args(argv)
    try:
        if args.from_directory:
            result = stage(args.from_directory, args.destination)
        else:
            installer = ROOT / "evofox-blaze.exe"
            if hashlib.sha256(installer.read_bytes()).hexdigest() != INSTALLER_SHA256:
                raise ValueError("Installer hash differs from the documented reference")
            temporary_root = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
            with tempfile.TemporaryDirectory(prefix="evofox-ui-", dir=temporary_root) as directory:
                subprocess.run([args.extractor, "--extract", "--silent", "--output-dir", directory,
                                str(installer)], check=True)
                result = stage(Path(directory) / "app/skins", args.destination)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Cannot prepare UI artwork: {error}\n")
    print(f"Local reference artwork ready: {result}")
    print("Launch: python3 -m evofox_blaze.gui")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
