from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .issue import Issue


@dataclass
class Tissue:
    cwd: Path

    def list_in_progress(self) -> list[dict[str, Any]]:
        issues = Issue.from_workdir(self.cwd)
        return issues.list(status="in_progress", limit=1000)
