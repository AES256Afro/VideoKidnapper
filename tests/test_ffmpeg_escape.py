from videokidnapper.utils.ffmpeg_escape import (
    escape_drawtext_value, escape_path, quote_filter_value,
)


def test_plain_text_passes_through():
    assert escape_drawtext_value("Hello world") == "Hello world"


def test_escapes_colons_and_commas():
    out = escape_drawtext_value("a:b,c")
    assert ":" not in out.replace("\\:", "")
    assert "," not in out.replace("\\,", "")


def test_escapes_brackets_and_semicolons():
    # These would terminate a filter chain if unescaped.
    out = escape_drawtext_value("evil[a];b]payload")
    assert "[" not in out.replace("\\[", "")
    assert "]" not in out.replace("\\]", "")
    assert ";" not in out.replace("\\;", "")


def test_single_quote_substituted():
    # We substitute ' with a curly quote to avoid the single-quote-inside-
    # single-quote ffmpeg escaping problem.
    out = escape_drawtext_value("don't")
    assert "'" not in out
    assert "\u2019" in out


def test_newlines_preserved():
    # ffmpeg drawtext treats raw \n as a newline; pass it through.
    assert "\n" in escape_drawtext_value("line1\nline2")


def test_escape_path_windows():
    p = escape_path(r"C:\Windows\Fonts\arial.ttf")
    assert "\\:" in p or p.startswith("C")
    assert "\\" not in p.replace("\\\\", "").replace("\\:", "").replace("\\'", "")


def test_empty_inputs():
    assert escape_drawtext_value(None) == ""
    assert escape_drawtext_value("") == ""
    assert escape_path(None) == ""


def test_quote_wraps():
    assert quote_filter_value("hi") == "'hi'"
