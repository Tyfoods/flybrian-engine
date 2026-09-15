"""Acquire the exact retained body model without duplicating existing assets."""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data"
SOURCE = "https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/a03e87bf13502b0b48ebbf2808928fd96ebf9cf3/flybody"


def _verify_asset(path: Path, size_bytes: int, sha256: str) -> None:
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if path.stat().st_size != size_bytes or digest != sha256:
        raise ValueError(f"Body model asset differs from the captured model: {path.name}")


def verify_body_assets(root: Path) -> None:
    for item in json.loads((DATA / "walking-body-model.json").read_text())["files"]:
        _verify_asset(root / item["path"], item["size_bytes"], item["sha256"])


def acquire_body_assets(root: Path) -> None:
    """Reuse present files; download missing files and verify the complete captured model."""
    import certifi

    context = ssl.create_default_context(cafile=certifi.where())
    for item in json.loads((DATA / "walking-body-model.json").read_text())["files"]:
        target = root / item["path"]
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")
        print(f"Preparing body model: {item['path']}", flush=True)
        with (
            urllib.request.urlopen(
                f"{SOURCE}/{item['path']}", context=context, timeout=60
            ) as response,
            partial.open("wb") as output,
        ):
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if item["path"] == "fruitfly.xml":
            text = partial.read_text()
            for original, retained in (
                (
                    '<general ctrllimited="true"/>',
                    '<general ctrllimited="true" dyntype="filter" dynprm="0.01 0 0"/>',
                ),
                (
                    '<general dyntype="none" dynprm="1"/>',
                    '<general dyntype="filter" dynprm="0.007 0 0"/>',
                ),
            ):
                if text.count(original) != 1:
                    raise ValueError("Upstream body model differs from the retained derivation.")
                text = text.replace(original, retained)
            partial.write_text(text)
        _verify_asset(partial, item["size_bytes"], item["sha256"])
        partial.replace(target)
    verify_body_assets(root)
    for name in ("walking-body-LICENSE.txt", "walking-body-NOTICE.txt", "walking-body-README.md"):
        target = root / name
        content = (DATA / name).read_bytes()
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)
