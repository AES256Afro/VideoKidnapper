# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Exports keep the source's colour: real ffmpeg, real files, measured.

Phone video is usually HDR (HLG or PQ, 10-bit BT.2020). Before the
colour pipeline in ``core.ffmpeg.color`` existed, exports of it came out
about 26 levels darker with a third of the saturation, and MP4s stayed
10-bit HDR that many players can't show. These tests grade one SDR test
card into each kind of source the way cameras do (reference white at
203 nits for HDR), export it, and compare what a correct player would
show against the SDR original.
"""

import json
import shutil
import subprocess

import pytest

np = pytest.importorskip("numpy")

from videokidnapper.core.ffmpeg import color  # noqa: E402
from videokidnapper.core.ffmpeg.encode import trim_to_gif, trim_to_video  # noqa: E402

ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None
pytestmark = pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg / ffprobe not on PATH")

W, H = 1280, 720          # HD, so untagged files mean BT.709 to players
CMP = (320, 180)          # compare at this size to average out codec noise
TAG709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
CARD = (f"smptehdbars=s={W}x{H // 2}:r=24:d=1.5[a];"
        f"testsrc2=s={W}x{H // 2}:r=24:d=1.5,format=yuv420p[b];[a][b]vstack")


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Surface ffmpeg's own message; CI logs are useless without it.
        raise AssertionError(
            f"ffmpeg failed ({result.returncode}): {result.stderr[-800:]}\n{cmd}")


def _has_hevc():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                         capture_output=True, text=True).stdout
    return "libx265" in out


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    d = tmp_path_factory.mktemp("color")
    srcs = {}
    sdr = d / "sdr709.mp4"
    _run(["ffmpeg", "-v", "error", "-y", "-filter_complex",
          f"{CARD},scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
          "-c:v", "libx264", "-crf", "8", *TAG709, "-color_range", "tv", str(sdr)])
    srcs["sdr709"] = sdr

    full = d / "fullrange.mp4"
    _run(["ffmpeg", "-v", "error", "-y", "-filter_complex",
          f"{CARD},scale=out_color_matrix=bt709:out_range=pc,format=yuvj420p",
          "-c:v", "libx264", "-crf", "8", *TAG709, "-color_range", "pc", str(full)])
    srcs["fullrange"] = full

    untagged = d / "untagged.mp4"
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(sdr), "-c", "copy", "-bsf:v",
          "h264_metadata=colour_primaries=2:transfer_characteristics=2:matrix_coefficients=2",
          str(untagged)])
    srcs["untagged"] = untagged

    if color.can_tonemap() and _has_hevc():
        for name, trc in (("hlg", "arib-std-b67"), ("pq", "smpte2084")):
            out = d / f"{name}.mp4"
            # npl=203 on the step that writes the HDR transfer: SDR white
            # lands on BT.2408 reference white, as camera footage does.
            _run(["ffmpeg", "-v", "error", "-y", "-i", str(sdr), "-vf",
                  "zscale=min=709:pin=709:tin=709:rin=limited"
                  ":t=linear:m=gbr:p=709:r=full,format=gbrpf32le,"
                  "zscale=min=gbr:tin=linear:pin=709:rin=full"
                  f":p=2020:t={trc}:npl=203:m=2020_ncl:r=limited,"
                  "format=yuv420p10le",
                  "-c:v", "libx265", "-x265-params", "log-level=error", "-crf", "8",
                  "-colorspace", "bt2020nc", "-color_primaries", "bt2020",
                  "-color_trc", trc, "-color_range", "tv", str(out)])
            srcs[name] = out
    return srcs


def _stream(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,pix_fmt,color_range,color_space,color_transfer",
         "-of", "json", str(path)], capture_output=True, text=True).stdout
    return json.loads(out)["streams"][0]


def _decode(path, t=0.75):
    """RGB of one frame, as a player honouring the file's tags shows it."""
    st = _stream(path)
    w, h = CMP
    if st["codec_name"] == "gif":
        vf = f"scale={w}:{h}:flags=area,format=rgb24"
    else:
        matrix = {"bt709": "bt709", "bt2020nc": "bt2020"}.get(st.get("color_space"), "bt709")
        rng = "pc" if st.get("color_range") == "pc" else "tv"
        vf = (f"scale={w}:{h}:flags=area:in_color_matrix={matrix}:in_range={rng},"
              "format=rgb24")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path),
                          "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3).astype(float)


def _luma(a):
    return (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]).mean()


def _sat(a):
    return (a.max(-1) - a.min(-1)).mean()


def _assert_matches(out, ref, what):
    luma_shift = _luma(out) - _luma(ref)
    sat_ratio = _sat(out) / _sat(ref)
    # Before the fix an HDR export measured luma -26, saturation 0.38.
    assert abs(luma_shift) < 3.0, f"{what}: luma shifted {luma_shift:+.1f}"
    assert 0.93 < sat_ratio < 1.07, f"{what}: saturation ratio {sat_ratio:.2f}"


@pytest.mark.parametrize("kind", ["sdr709", "fullrange", "untagged", "hlg", "pq"])
def test_mp4_export_matches_source(sources, tmp_path, kind):
    if kind not in sources:
        pytest.skip("this ffmpeg can't make/tone-map HDR test footage")
    out = trim_to_video(str(sources[kind]), 0.0, 1.2, "High",
                        str(tmp_path / "out.mp4"), options={"hw_encoder": "off"})
    assert out
    st = _stream(out)
    # 8-bit BT.709 limited, tagged: plays everywhere, no guessing.
    assert st["pix_fmt"] == "yuv420p"
    assert st.get("color_space") == "bt709"
    assert st.get("color_transfer") == "bt709"
    assert st.get("color_range") == "tv"
    _assert_matches(_decode(out), _decode(sources["sdr709"]), f"{kind} mp4")


@pytest.mark.parametrize("kind", ["sdr709", "untagged", "hlg"])
def test_gif_export_matches_source(sources, tmp_path, kind):
    if kind not in sources:
        pytest.skip("this ffmpeg can't make/tone-map HDR test footage")
    out = trim_to_gif(str(sources[kind]), 0.0, 1.2, "High",
                      str(tmp_path / "out.gif"), options={"gif_dither": "none"})
    assert out
    _assert_matches(_decode(out), _decode(sources["sdr709"]), f"{kind} gif")


def test_sticker_keeps_its_colour(sources, tmp_path):
    """A pure-red sticker must export pure red, not SD-matrix red."""
    from PIL import Image

    sticker = tmp_path / "red.png"
    Image.new("RGBA", (200, 200), (220, 30, 30, 255)).save(sticker)
    out = trim_to_video(
        str(sources["sdr709"]), 0.0, 1.2, "Ultra", str(tmp_path / "out.mp4"),
        image_layers=[{"path": str(sticker), "position": "center", "scale": 1.0,
                       "start": 0, "end": 99}],
        options={"hw_encoder": "off"},
    )
    assert out
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(out), "-frames:v", "1",
         "-vf", "scale=in_color_matrix=bt709:in_range=tv,format=rgb24",
         "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(float)
    patch = frame[H // 2 - 40:H // 2 + 40, W // 2 - 40:W // 2 + 40].mean((0, 1))
    assert np.abs(patch - [220, 30, 30]).max() < 8, patch


@pytest.mark.parametrize("fmt", ["mp4", "gif"])
def test_export_survives_an_ffmpeg_whose_zscale_rejects_the_chain(
        sources, tmp_path, monkeypatch, fmt):
    """zimg differs between ffmpeg builds. If this build's zscale refuses
    the HDR conversion, export with the plain conversion instead of
    failing outright."""
    if "hlg" not in sources:
        pytest.skip("this ffmpeg can't make/tone-map HDR test footage")
    # A chain zscale is guaranteed to reject stands in for such a build.
    monkeypatch.setattr(color, "_tonemap_chain",
                        lambda *_a: "zscale=tin=linear:t=bogus,format=yuv420p")
    monkeypatch.setattr(color, "_tonemap_broken", False)
    fn = trim_to_video if fmt == "mp4" else trim_to_gif
    out = fn(str(sources["hlg"]), 0.0, 1.0, "Low", str(tmp_path / f"out.{fmt}"),
             options={"hw_encoder": "off"})
    assert out and (tmp_path / f"out.{fmt}").stat().st_size > 0
    assert color._tonemap_broken, "the failing chain should be switched off"
