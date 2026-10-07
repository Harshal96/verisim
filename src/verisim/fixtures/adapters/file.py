"""Read a normalized branch catalog from a project-relative JSON file."""

from __future__ import annotations

import json
from pathlib import Path


def load_branches(*, options: dict, context: dict) -> dict:
    if set(options) != {"path"} or not isinstance(options["path"], str):
        raise ValueError("file catalog adapter requires only a string path option")
    path = (Path(context["project_root"]) / options["path"]).resolve()
    return json.loads(path.read_text(encoding="utf-8"))
