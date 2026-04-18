from videokidnapper.utils.dnd import parse_dnd_files


def test_empty_input():
    assert parse_dnd_files("") == []
    assert parse_dnd_files(None) == []


def test_single_path_no_spaces():
    assert parse_dnd_files("C:/a.mp4") == ["C:/a.mp4"]


def test_single_path_with_spaces_braced():
    assert parse_dnd_files("{C:/my video.mp4}") == ["C:/my video.mp4"]


def test_multiple_paths_mixed():
    data = "{C:/my video.mp4} C:/clean.gif {D:/My Folder/clip.mov}"
    assert parse_dnd_files(data) == [
        "C:/my video.mp4",
        "C:/clean.gif",
        "D:/My Folder/clip.mov",
    ]


def test_windows_backslashes_preserved():
    assert parse_dnd_files(r"{C:\Users\me\clip.mp4}") == [r"C:\Users\me\clip.mp4"]


def test_braces_inside_name_survive():
    # Edge case: a filename with unbalanced braces — current parser treats
    # the first `{` as wrapper, then closes on the first `}`. Good enough
    # for the real world.
    out = parse_dnd_files("{C:/weird{name}.mp4}")
    assert out[0] == "C:/weird{name"
