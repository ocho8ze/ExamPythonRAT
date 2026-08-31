"""Tests unitaires pour le module commands."""

import os
import tempfile
from pathlib import Path

from exampythonrat.commands import (
    cmd_download,
    cmd_help,
    cmd_ipconfig,
    cmd_search,
    cmd_shell,
    cmd_upload,
)


class TestCmdHelp:
    def test_returns_string(self):
        result = cmd_help()
        assert isinstance(result, str)

    def test_contains_commands(self):
        result = cmd_help()
        assert "help" in result
        assert "download" in result
        assert "upload" in result
        assert "shell" in result
        assert "ipconfig" in result
        assert "screenshot" in result
        assert "search" in result
        assert "hashdump" in result
        assert "keylogger" in result
        assert "webcam_snapshot" in result
        assert "webcam_stream" in result
        assert "record_audio" in result


class TestCmdShell:
    def test_simple_command(self):
        result = cmd_shell("echo hello")
        assert "hello" in result

    def test_invalid_command(self):
        result = cmd_shell("commande_qui_nexiste_pas_12345")
        assert result != ""

    def test_multiword_command(self):
        result = cmd_shell("echo foo bar")
        assert "foo bar" in result


class TestCmdIpconfig:
    def test_returns_string(self):
        result = cmd_ipconfig()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCmdDownload:
    def test_download_existing_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"contenu test")
            tmp_path = f.name
        try:
            result = cmd_download(tmp_path)
            assert isinstance(result, tuple)
            data, filename = result
            assert data == b"contenu test"
            assert filename.endswith(".txt")
        finally:
            os.unlink(tmp_path)

    def test_download_nonexistent_file(self):
        result = cmd_download("/chemin/inexistant/fichier.txt")
        assert isinstance(result, str)
        assert "Erreur" in result

    def test_download_directory(self):
        result = cmd_download(tempfile.gettempdir())
        assert isinstance(result, str)
        assert "Erreur" in result


class TestCmdUpload:
    def test_upload_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "uploaded.txt")
            result = cmd_upload(filepath, b"data envoyee")
            assert "envoyé" in result or "Fichier" in result
            assert Path(filepath).read_bytes() == b"data envoyee"

    def test_upload_creates_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "sub", "dir", "file.txt")
            cmd_upload(filepath, b"nested data")
            assert Path(filepath).exists()
            assert Path(filepath).read_bytes() == b"nested data"


class TestCmdSearch:
    def test_search_finds_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.txt").write_text("a")
            Path(tmpdir, "test.log").write_text("b")
            Path(tmpdir, "sub").mkdir()
            Path(tmpdir, "sub", "deep.txt").write_text("c")

            result = cmd_search(tmpdir, "*.txt")
            assert "test.txt" in result
            assert "deep.txt" in result
            assert "test.log" not in result

    def test_search_no_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = cmd_search(tmpdir, "*.xyz")
            assert "Aucun" in result

    def test_search_invalid_directory(self):
        result = cmd_search("/chemin/inexistant", "*.txt")
        assert "Erreur" in result
