"""Tests unitaires pour le module protocol."""

import socket

import pytest

from exampythonrat.crypto import CryptoHandler, generate_key
from exampythonrat.protocol import Protocol


class FakeSocketPair:
    """Crée une paire de sockets connectées pour les tests."""

    def __init__(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", 0))
        self.server_sock.listen(1)
        self.port = self.server_sock.getsockname()[1]

        self.client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_sock.connect(("127.0.0.1", self.port))

        self.accepted_sock, _ = self.server_sock.accept()

    def close(self):
        self.client_sock.close()
        self.accepted_sock.close()
        self.server_sock.close()


@pytest.fixture()
def socket_pair():
    pair = FakeSocketPair()
    yield pair
    pair.close()


@pytest.fixture()
def shared_key():
    return generate_key()


class TestProtocolSendRecv:
    def test_send_recv_simple_message(self, socket_pair, shared_key):
        crypto = CryptoHandler(shared_key)
        sender = Protocol(socket_pair.client_sock, crypto)
        receiver = Protocol(socket_pair.accepted_sock, crypto)

        message = {"type": "command", "command": "help", "args": []}
        sender.send(message)
        received = receiver.recv()

        assert received == message

    def test_send_recv_with_data(self, socket_pair, shared_key):
        crypto = CryptoHandler(shared_key)
        sender = Protocol(socket_pair.client_sock, crypto)
        receiver = Protocol(socket_pair.accepted_sock, crypto)

        message = {"type": "response", "command": "ipconfig", "data": "eth0: 192.168.1.1"}
        sender.send(message)
        received = receiver.recv()

        assert received == message
        assert received["data"] == "eth0: 192.168.1.1"

    def test_multiple_messages(self, socket_pair, shared_key):
        crypto = CryptoHandler(shared_key)
        sender = Protocol(socket_pair.client_sock, crypto)
        receiver = Protocol(socket_pair.accepted_sock, crypto)

        messages = [
            {"type": "command", "command": "help", "args": []},
            {"type": "command", "command": "ipconfig", "args": []},
            {"type": "command", "command": "shell", "args": ["ls"]},
        ]
        for msg in messages:
            sender.send(msg)

        for expected in messages:
            received = receiver.recv()
            assert received == expected

    def test_recv_returns_none_on_disconnect(self, socket_pair, shared_key):
        crypto = CryptoHandler(shared_key)
        receiver = Protocol(socket_pair.accepted_sock, crypto)
        socket_pair.client_sock.close()

        result = receiver.recv()
        assert result is None


class TestProtocolHelpers:
    def test_send_response(self, socket_pair, shared_key):
        crypto = CryptoHandler(shared_key)
        sender = Protocol(socket_pair.client_sock, crypto)
        receiver = Protocol(socket_pair.accepted_sock, crypto)

        sender.send_response("test_cmd", "résultat ok")
        received = receiver.recv()

        assert received["type"] == "response"
        assert received["command"] == "test_cmd"
        assert received["data"] == "résultat ok"
        assert received["status"] == "success"

    def test_send_response_error(self, socket_pair, shared_key):
        crypto = CryptoHandler(shared_key)
        sender = Protocol(socket_pair.client_sock, crypto)
        receiver = Protocol(socket_pair.accepted_sock, crypto)

        sender.send_response("test_cmd", "erreur ici", "error")
        received = receiver.recv()

        assert received["status"] == "error"

    def test_send_command(self, socket_pair, shared_key):
        crypto = CryptoHandler(shared_key)
        sender = Protocol(socket_pair.client_sock, crypto)
        receiver = Protocol(socket_pair.accepted_sock, crypto)

        sender.send_command("shell", ["ls", "-la"])
        received = receiver.recv()

        assert received["type"] == "command"
        assert received["command"] == "shell"
        assert received["args"] == ["ls", "-la"]

    def test_send_file_response(self, socket_pair, shared_key):
        crypto = CryptoHandler(shared_key)
        sender = Protocol(socket_pair.client_sock, crypto)
        receiver = Protocol(socket_pair.accepted_sock, crypto)

        file_data = b"\x89PNG\r\n\x1a\nfakeimage"
        sender.send_file_response("screenshot", file_data, "screenshot.png")
        received = receiver.recv()

        assert received["filename"] == "screenshot.png"
        assert received["status"] == "success"

        import base64

        decoded = base64.b64decode(received["data"])
        assert decoded == file_data
