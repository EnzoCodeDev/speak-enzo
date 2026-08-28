"""Envío de texto al chatbox de VRChat vía OSC (UDP 127.0.0.1:9000).

Requiere tener OSC activado dentro de VRChat:
Action Menu → Options → OSC → Enabled.
"""

import socket

VRCHAT_OSC = ("127.0.0.1", 9000)


def _pad(b):
    return b + b"\x00" * (4 - len(b) % 4)


def send_chatbox(text, immediate=True, notify=False):
    """Escribe `text` en el chatbox de VRChat."""
    text = text[:144]  # límite del chatbox
    addr = _pad(b"/chatbox/input")
    tags = _pad(b"," + b"s" + (b"T" if immediate else b"F")
                + (b"T" if notify else b"F"))
    data = addr + tags + _pad(text.encode("utf-8"))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(data, VRCHAT_OSC)
        sock.close()
        return True
    except OSError:
        return False
