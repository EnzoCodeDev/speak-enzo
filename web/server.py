"""Servidor local de Enzo Speak con búsqueda y práctica de canciones."""

from __future__ import annotations

import json
import re
import threading
import urllib.request
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
SONGS_INDEX = ROOT / "songs" / "index.json"
SONGS_LOCK = threading.Lock()


def _source_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("La fuente de la canción no es válida.")
    return value.strip()


def _lrclib_lines(record: dict) -> list[dict]:
    synced = record.get("syncedLyrics") or ""
    lines = []
    for row in synced.splitlines():
        match = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)", row)
        if match and _clean_line(match.group(3)):
            lines.append({"text": _clean_line(match.group(3)),
                          "start": round(int(match.group(1)) * 60 + float(match.group(2)), 2)})
    if lines:
        return lines
    return [{"text": text, "start": 0} for row in (record.get("plainLyrics") or "").splitlines()
            if (text := _clean_line(row))]


def search_lyrics(query: str) -> dict:
    query = query.strip()
    if len(query) < 2:
        raise ValueError("Escribe el nombre de la canción y, si puedes, el artista.")
    url = "https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(url, headers={"User-Agent": "EnzoSpeak/0.2 (local learning app)"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            records = json.load(response)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("No pude consultar el catálogo de letras. Intenta nuevamente.") from exc
    results = []
    for record in records[:10]:
        lines = _lrclib_lines(record)
        if not lines or record.get("instrumental"):
            continue
        results.append({"id": record.get("id"), "title": record.get("trackName") or record.get("name"),
                        "artist": record.get("artistName") or "", "album": record.get("albumName") or "",
                        "duration": record.get("duration"), "synced": bool(record.get("syncedLyrics")),
                        "lines": lines})
    return {"results": results}


def _clean_line(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[[^]]+]", "", text)
    return re.sub(r"\s+", " ", text).strip(" -\n")


def save_song(data: dict) -> dict:
    url = _source_url(str(data.get("url", "")))
    song_id = str(data.get("song_id", "")).strip()
    title = str(data.get("title", "")).strip()
    lines = data.get("lines")
    if not song_id or not title or not isinstance(lines, list) or not lines:
        raise ValueError("Faltan los datos de la canción para guardarla.")

    song = {
        "song_id": song_id,
        "title": title,
        "url": url,
        "source": str(data.get("source", "lrclib")),
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lines": [
            {"text": str(line.get("text", "")), "translation_es": str(line.get("es", "")),
             "pronunciation_es": str(line.get("phon_es", "")), "start": line.get("start", 0)}
            for line in lines if isinstance(line, dict) and line.get("text")
        ],
    }
    if not song["lines"]:
        raise ValueError("La canción no contiene frases válidas.")

    with SONGS_LOCK:
        SONGS_INDEX.parent.mkdir(parents=True, exist_ok=True)
        try:
            index = json.loads(SONGS_INDEX.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            index = {"songs": []}
        songs = index.get("songs", [])
        songs = [existing for existing in songs if existing.get("song_id") != song_id]
        songs.append(song)
        index = {"songs": songs}
        temporary = SONGS_INDEX.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(SONGS_INDEX)
    return song


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            encoded = json.dumps({"status": "ok", "server": "enzo-speak", "songs": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if parsed.path == "/api/lyrics/search":
            try:
                body, status = search_lyrics(parse_qs(parsed.query).get("q", [""])[0]), 200
            except (ValueError, RuntimeError) as exc:
                body, status = {"error": str(exc)}, 400
            encoded = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if parsed.path == "/api/songs":
            try:
                body = json.loads(SONGS_INDEX.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                body = {"songs": []}
            encoded = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/songs":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 5 * 1024 * 1024:
                raise ValueError("Los datos de la canción son demasiado grandes o están vacíos.")
            body = save_song(json.loads(self.rfile.read(length)))
            response, status = {"saved": True, "song": body}, 201
        except (ValueError, json.JSONDecodeError) as exc:
            response, status = {"error": str(exc)}, 400
        encoded = json.dumps(response, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8180)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
