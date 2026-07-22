# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Versioned VideoKidnapper project files and crash-recovery autosaves."""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from videokidnapper import __version__
from videokidnapper.utils import settings


PROJECT_EXTENSION = ".vidkid"
SCHEMA_VERSION = 1
AUTOSAVE_NAME = ".videokidnapper_autosave.vidkid"


class ProjectFileError(ValueError):
    pass


def autosave_path():
    """Keep recovery data beside settings, including isolated test settings."""
    return settings._SETTINGS_PATH.with_name(AUTOSAVE_NAME)


def build_document(source_path, editor_state, export_state, project_path=None):
    source = Path(source_path).expanduser().resolve()
    project_file = Path(project_path).expanduser().resolve() if project_path else None
    return {
        "schema_version": SCHEMA_VERSION,
        "app_version": __version__,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "project_path": str(project_file) if project_file else "",
        "linked_project_path": str(project_file) if project_file else "",
        "source": _portable_path(source, project_file),
        "editor": _prepare_editor_paths(editor_state, project_file),
        "export": dict(export_state or {}),
    }


def save_document(path, document):
    """Write JSON beside its destination, then atomically replace it."""
    target = Path(path).expanduser()
    if target.suffix.lower() != PROJECT_EXTENSION:
        target = target.with_suffix(PROJECT_EXTENSION)
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    data = dict(document)
    data["schema_version"] = SCHEMA_VERSION
    data["project_path"] = str(target)
    data["saved_at"] = datetime.now(timezone.utc).isoformat()

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.stem}.", suffix=".tmp", dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target


def load_document(path):
    project_file = Path(path).expanduser().resolve()
    try:
        with open(project_file, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectFileError(f"Could not read project: {exc}") from exc
    if not isinstance(data, dict):
        raise ProjectFileError("Project root must be a JSON object")
    version = data.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise ProjectFileError("Project schema version is missing or invalid")
    if version > SCHEMA_VERSION:
        raise ProjectFileError(
            f"This project needs a newer VideoKidnapper (schema {version})",
        )
    if not isinstance(data.get("editor"), dict):
        raise ProjectFileError("Project editor state is missing")
    if not isinstance(data.get("source"), dict):
        raise ProjectFileError("Project source is missing")
    if not (
        data["source"].get("path") or data["source"].get("relative_path")
    ):
        raise ProjectFileError("Project source path is missing")
    if not isinstance(data.get("export", {}), dict):
        raise ProjectFileError("Project export state must be an object")
    editor = data["editor"]
    range_value = editor.get("range")
    if not _valid_range(range_value):
        raise ProjectFileError("Project trim range is missing or invalid")
    for key in ("queued", "layers", "images"):
        value = editor.get(key, [])
        if not isinstance(value, list):
            raise ProjectFileError(f"Project {key} must be a list")
    if any(not _valid_range(item) for item in editor.get("queued", [])):
        raise ProjectFileError("Project queued ranges are invalid")
    for key in ("layers", "images"):
        if any(not isinstance(item, dict) for item in editor.get(key, [])):
            raise ProjectFileError(f"Project {key} entries must be objects")
    linked = data.get("linked_project_path") or ""
    resolution_file = Path(linked).expanduser().resolve() if linked else project_file
    data["editor"] = _resolve_editor_paths(data["editor"], resolution_file)
    data["resolved_source"] = str(
        _resolve_portable_path(data["source"], resolution_file),
    )
    return data


def delete_autosave():
    try:
        autosave_path().unlink(missing_ok=True)
    except OSError:
        pass


def _portable_path(path, project_file):
    result = {"path": str(path), "relative_path": ""}
    if project_file:
        try:
            result["relative_path"] = os.path.relpath(path, project_file.parent)
        except (OSError, ValueError):
            pass
    return result


def _valid_range(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        return False
    return all(math.isfinite(float(item)) for item in value)


def _resolve_portable_path(value, project_file):
    relative = value.get("relative_path") or ""
    if relative:
        candidate = (project_file.parent / relative).resolve()
        if candidate.exists():
            return candidate
    return Path(value.get("path") or "").expanduser().resolve()


def _prepare_editor_paths(editor_state, project_file):
    editor = dict(editor_state or {})
    images = []
    for raw in editor.get("images", []):
        layer = dict(raw)
        path = layer.get("path")
        if path:
            layer["source"] = _portable_path(Path(path).expanduser().resolve(), project_file)
        images.append(layer)
    editor["images"] = images
    return editor


def _resolve_editor_paths(editor_state, project_file):
    editor = dict(editor_state or {})
    images = []
    for raw in editor.get("images", []):
        layer = dict(raw)
        if isinstance(layer.get("source"), dict):
            layer["path"] = str(_resolve_portable_path(layer["source"], project_file))
        images.append(layer)
    editor["images"] = images
    return editor
