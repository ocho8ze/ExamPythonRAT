"""Protocole de communication TCP avec framing et chiffrement."""

import base64
import json
import logging
import socket
import struct
from typing import Any

from .crypto import CryptoHandler

logger = logging.getLogger(__name__)

HEADER_SIZE = 4
MAX_MESSAGE_SIZE = 50 * 1024 * 1024


class Protocol:
    """Gère le framing, la sérialisation et le chiffrement des messages TCP.

    Format fil : [4 octets longueur big-endian] [payload chiffré Fernet]
    Payload déchiffré : objet JSON.
    """

    def __init__(self, sock: socket.socket, crypto: CryptoHandler):
        self._sock = sock
        self._crypto = crypto

    def send(self, message: dict[str, Any]) -> None:
        """Sérialise, chiffre et envoie un message."""
        payload = json.dumps(message).encode()
        encrypted = self._crypto.encrypt(payload)
        header = struct.pack(">I", len(encrypted))
        self._sock.sendall(header + encrypted)
        logger.debug("Sent message: command=%s", message.get("command", message.get("type")))

    def recv(self) -> dict[str, Any] | None:
        """Reçoit, déchiffre et désérialise un message."""
        header = self._recv_exact(HEADER_SIZE)
        if header is None:
            return None
        length = struct.unpack(">I", header)[0]
        if length > MAX_MESSAGE_SIZE:
            logger.error("Message trop volumineux: %d octets", length)
            return None
        encrypted = self._recv_exact(length)
        if encrypted is None:
            return None
        payload = self._crypto.decrypt(encrypted)
        return json.loads(payload)

    def _recv_exact(self, n: int) -> bytes | None:
        """Reçoit exactement n octets depuis le socket."""
        data = b""
        while len(data) < n:
            chunk = self._sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def send_response(self, command: str, data: str, status: str = "success") -> None:
        """Envoie une réponse textuelle."""
        self.send(
            {
                "type": "response",
                "command": command,
                "data": data,
                "status": status,
            }
        )

    def send_file_response(self, command: str, file_data: bytes, filename: str) -> None:
        """Envoie un fichier encodé en base64."""
        self.send(
            {
                "type": "response",
                "command": command,
                "data": base64.b64encode(file_data).decode(),
                "filename": filename,
                "status": "success",
            }
        )

    def send_command(self, command: str, args: list[str] | None = None, data: str = "") -> None:
        """Envoie une commande au client."""
        self.send(
            {
                "type": "command",
                "command": command,
                "args": args or [],
                "data": data,
            }
        )
