# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
from videokidnapper.utils.file_naming import generate_export_path


def test_respects_base_dir(tmp_path):
    out = generate_export_path("trim", "gif", base_dir=tmp_path)
    assert str(out).startswith(str(tmp_path))
    assert out.suffix == ".gif"


def test_collision_appends_counter(tmp_path):
    first = generate_export_path("trim", "gif", base_dir=tmp_path)
    first.write_text("")
    second = generate_export_path("trim", "gif", base_dir=tmp_path)
    # Either same-second with _1 suffix or next second with fresh name.
    assert second != first
    assert second.suffix == ".gif"


def test_strips_leading_dot_in_extension(tmp_path):
    out = generate_export_path("url", ".mp4", base_dir=tmp_path)
    assert out.suffix == ".mp4"
    assert ".." not in str(out)


def test_creates_missing_base_dir(tmp_path):
    nested = tmp_path / "deep" / "export"
    out = generate_export_path("trim", "mp4", base_dir=nested)
    assert nested.exists()
    assert str(out).startswith(str(nested))
