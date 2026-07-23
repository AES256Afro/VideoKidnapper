# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""End-to-end coverage for the native direct-media download path."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from videokidnapper.core import downloader


@pytest.fixture
def local_media_server():
    payload = (b"VideoKidnapper-native-stream\x00" * 5000) + b"complete"

    class MediaHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not self.path.startswith("/clip.mp4"):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            for start in range(0, len(payload), 8192):
                self.wfile.write(payload[start:start + 8192])

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), MediaHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/clip.mp4?token=test", payload
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_native_provider_streams_media_from_http_server(
    local_media_server, tmp_path, monkeypatch,
):
    url, payload = local_media_server
    progress = []
    monkeypatch.setattr(downloader, "TEMP_DIR", tmp_path)

    result = downloader.download_video(
        url,
        progress_callback=lambda fraction, message: progress.append(
            (fraction, message)
        ),
    )

    assert result["error"] is None
    assert result["provider"] == "VideoKidnapper native"
    assert result["title"] == "clip"
    assert (tmp_path / "clip.mp4").read_bytes() == payload
    assert result["path"] == str(tmp_path / "clip.mp4")
    assert progress[-1] == (0.95, "Opening native download...")
    assert list(tmp_path.glob("*.part")) == []
