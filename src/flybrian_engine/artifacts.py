"""Versioned run artifact manifest shared by local and cloud consumers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Artifact:
    key: str
    kind: str
    media_type: str
    relative_path: str
    size_bytes: int
    sha256: str

    @classmethod
    def from_file(cls, *, key: str, kind: str, media_type: str, path: Path, root: Path) -> Artifact:
        data = path.read_bytes()
        return cls(
            key=key,
            kind=kind,
            media_type=media_type,
            relative_path=path.relative_to(root).as_posix(),
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )


@dataclass(frozen=True)
class ArtifactManifest:
    run_id: str
    backend_id: str
    backend_version: str
    experiment_sha256: str
    artifacts: tuple[Artifact, ...]
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def write(self, path: Path) -> None:
        content = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        path.write_text(content, encoding="utf-8")
