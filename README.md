# ExamPythonRAT

Remote Administration Tool (RAT) éducatif développé en Python dans le cadre du cours de Sécurité Python (ESGI 4A).

## Architecture

Le projet est composé de deux programmes :

- **Serveur (`rat-server`)** : interface de commande interactive (C2) qui écoute les connexions entrantes et permet de contrôler les agents connectés.
- **Client (`rat-client`)** : agent qui se connecte au serveur, reçoit et exécute les commandes.

### Communication

- Transport : TCP
- Chiffrement : Fernet (AES-128-CBC + HMAC-SHA256) via la bibliothèque `cryptography`
- Framing : préfixe de longueur 4 octets (big-endian) + payload chiffré
- Sérialisation : JSON

### Modules

```
src/exampythonrat/
├── __init__.py       # Version du package
├── crypto.py         # Chiffrement / déchiffrement Fernet
├── protocol.py       # Framing TCP et sérialisation des messages
├── commands.py       # Implémentation des commandes (côté client)
├── client.py         # Agent RAT
└── server.py         # Serveur C2 multi-agents
```

## Installation

### Prérequis

- Python >= 3.12
- Poetry

### Mise en place

```bash
git clone <url-du-repo>
cd ExamPythonRAT
poetry install
pre-commit install
```

### Dépendances système (optionnelles)

- **PortAudio** (pour `record_audio`) :
  - Ubuntu/Debian : `sudo apt install portaudio19-dev`
  - macOS : `brew install portaudio`
  - Windows : inclus avec PyAudio

## Utilisation

### 1. Démarrer le serveur

```bash
poetry run rat-server --port 8888
```

Le serveur génère une clé de chiffrement au démarrage. Notez-la pour le client.

Vous pouvez aussi fournir votre propre clé :

```bash
poetry run rat-server --port 8888 --key "votre-clé-fernet"
```

### 2. Démarrer le client (agent)

```bash
poetry run rat-client --host 127.0.0.1 --port 8888 --key "clé-du-serveur"
```

Le client se reconnecte automatiquement en cas de déconnexion. Désactivable avec `--no-reconnect`.

### 3. Interface du serveur

#### Menu principal

| Commande          | Description                    |
|-------------------|--------------------------------|
| `sessions`        | Lister les agents connectés    |
| `interact <id>`   | Interagir avec un agent        |
| `kill <id>`       | Déconnecter un agent           |
| `help`            | Afficher l'aide                |
| `exit`            | Arrêter le serveur             |

#### Commandes agent

| Commande                      | Description                            |
|-------------------------------|----------------------------------------|
| `help`                        | Afficher les commandes disponibles     |
| `download <chemin>`           | Télécharger un fichier depuis l'agent  |
| `upload <local> [distant]`    | Envoyer un fichier vers l'agent        |
| `shell`                       | Shell interactif                       |
| `shell <commande>`            | Exécuter une commande unique           |
| `ipconfig`                    | Configuration réseau                   |
| `screenshot`                  | Capture d'écran                        |
| `search <chemin> <motif>`     | Rechercher des fichiers                |
| `hashdump`                    | Dump des hash (SAM/shadow)             |
| `keylogger <start\|stop\|dump>` | Gérer le keylogger                   |
| `webcam_snapshot`             | Photo webcam                           |
| `webcam_stream <secondes>`    | Enregistrement vidéo webcam            |
| `record_audio <secondes>`     | Enregistrement audio                   |
| `back`                        | Revenir au menu principal              |

Les fichiers récupérés (screenshots, vidéos, etc.) sont sauvegardés dans le dossier `loot/`.

## Tests

```bash
poetry run pytest -v
```

## Linting

```bash
poetry run ruff check src/ tests/
poetry run ruff format src/ tests/
```

## Technologies utilisées

| Outil          | Usage                          |
|----------------|--------------------------------|
| Poetry         | Gestion des dépendances        |
| pre-commit     | Hooks de formatage (ruff)      |
| pytest         | Tests unitaires                |
| logging        | Journalisation (pas de print)  |
| cryptography   | Chiffrement Fernet             |
| mss            | Capture d'écran                |
| pynput         | Keylogger                      |
| opencv-python  | Webcam                         |
| pyaudio        | Enregistrement audio           |
