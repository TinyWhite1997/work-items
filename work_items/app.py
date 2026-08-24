#!/usr/bin/env python3
"""A local-first work-item server and CLI backed by SQLite. Requires Python 3.10+."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
TYPES = ("Epic", "Feature", "Task", "Bug")
STATUSES = ("open", "inprogress", "closed", "resolved", "blocked")
PRIORITIES = ("low", "medium", "high", "urgent")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def data_path() -> Path:
    default = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "work-items" / "items.db"
    return Path(os.environ.get("WORK_ITEMS_DATA", default))


def config_path() -> Path:
    return Path(os.environ.get("WORK_ITEMS_CONFIG", Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "work-items" / "config.json"))


def configured_url() -> str | None:
    url = os.environ.get("WORK_ITEMS_URL")
    if not url and config_path().exists():
        try:
            url = json.loads(config_path().read_text()).get("url")
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid CLI config: {config_path()}") from error
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("URL must be an http(s) server address, for example http://host:37481")
    return url.rstrip("/")


def configured_url_for(url: str) -> str:
    previous = os.environ.get("WORK_ITEMS_URL")
    os.environ["WORK_ITEMS_URL"] = url
    try:
        return configured_url() or ""
    finally:
        if previous is None:
            os.environ.pop("WORK_ITEMS_URL", None)
        else:
            os.environ["WORK_ITEMS_URL"] = previous


def remote_request(url: str, path: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except OSError as error:
        raise ValueError(f"Could not reach {url}: {error}") from error


class Store:
    """SQLite store with WAL transactions and a pre-write SQLite backup."""

    def __init__(self, path: Path):
        # A configured legacy JSON path migrates beside itself to a SQLite database.
        self.legacy_path = path if path.suffix == ".json" else path.with_suffix(".json")
        self.path = path.with_suffix(".db") if path.suffix == ".json" else path
        self.backups = self.path.parent / "backups"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS projects (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS items (
                  id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  type TEXT NOT NULL CHECK(type IN ('Epic','Feature','Task','Bug')),
                  description TEXT NOT NULL,
                  parent_id TEXT REFERENCES items(id),
                  project_id TEXT NOT NULL REFERENCES projects(id),
                  status TEXT NOT NULL CHECK(status IN ('open','inprogress','closed','resolved','blocked')),
                  priority TEXT NOT NULL CHECK(priority IN ('low','medium','high','urgent')),
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS items_project ON items(project_id);
                CREATE INDEX IF NOT EXISTS items_parent ON items(parent_id);
                """
            )
            migrated = connection.execute("SELECT 1 FROM metadata WHERE key = 'legacy_json_imported'").fetchone()
            empty = not connection.execute("SELECT 1 FROM projects LIMIT 1").fetchone() and not connection.execute("SELECT 1 FROM items LIMIT 1").fetchone()
            if self.legacy_path.exists() and not migrated and empty:
                self._migrate_json(connection)
                connection.execute("INSERT INTO metadata VALUES ('legacy_json_imported', ?)", (now(),))

    def _migrate_json(self, connection: sqlite3.Connection) -> None:
        """Import legacy JSON atomically; retain it as a recovery artifact."""
        try:
            raw = json.loads(self.legacy_path.read_text())
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid legacy data file: {self.legacy_path}") from error
        if isinstance(raw, list):
            raw = {"projects": [{"id": "general", "name": "General", "created_at": now(), "updated_at": now()}], "items": [{**item, "project_id": item.get("project_id", "general")} for item in raw]}
        if not isinstance(raw, dict) or not isinstance(raw.get("projects"), list) or not isinstance(raw.get("items"), list):
            raise ValueError(f"Legacy data file must contain projects and items: {self.legacy_path}")
        self.backups.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.legacy_path, self.backups / f"items-before-sqlite-{now().replace(':', '-')}.json")
        project_ids = set()
        for project in raw["projects"]:
            connection.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", (project["id"], project["name"], project.get("created_at", now()), project.get("updated_at", now())))
            project_ids.add(project["id"])
        if not project_ids and raw["items"]:
            connection.execute("INSERT INTO projects VALUES ('general', 'General', ?, ?)", (now(), now()))
            project_ids.add("general")
        # Insert all rows without parents first, then restore parent references. Legacy exports need not be tree ordered.
        for item in raw["items"]:
            project_id = item.get("project_id", "general")
            if project_id not in project_ids:
                raise ValueError(f"Legacy item references missing project: {project_id}")
            connection.execute(
                "INSERT INTO items VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)",
                (item["id"], item["title"], item["type"], item.get("description", ""), project_id, item.get("status", "open"), item.get("priority", "medium"), item.get("created_at", now()), item.get("updated_at", now())),
            )
        for item in raw["items"]:
            if item.get("parent_id"):
                connection.execute("UPDATE items SET parent_id = ? WHERE id = ?", (item["parent_id"], item["id"]))

    def _backup_before_write(self) -> Path:
        """Snapshot the last committed database before every mutation; keep 100 snapshots."""
        self.backups.mkdir(parents=True, exist_ok=True)
        target = self.backups / f"items-{now().replace(':', '-')}-{uuid.uuid4().hex[:6]}.db"
        with self._connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        old = sorted(self.backups.glob("items-*.db"))[:-100]
        for backup in old:
            backup.unlink()
        return target

    @contextmanager
    def transaction(self):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _rows(rows) -> list[dict]:
        return [dict(row) for row in rows]

    def projects(self) -> list[dict]:
        with self._connect() as connection:
            return self._rows(connection.execute("SELECT * FROM projects ORDER BY created_at"))

    def items(self, project_id: str | None = None) -> list[dict]:
        with self._connect() as connection:
            if project_id:
                return self._rows(connection.execute("SELECT * FROM items WHERE project_id = ? ORDER BY created_at", (project_id,)))
            return self._rows(connection.execute("SELECT * FROM items ORDER BY created_at"))

    def item(self, item_id: str) -> dict:
        with self._connect() as connection:
            item = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if not item:
                raise KeyError("item not found")
            return dict(item)

    def backup_list(self) -> list[dict]:
        return [{"path": str(path), "bytes": path.stat().st_size} for path in sorted(self.backups.glob("*"), reverse=True)] if self.backups.exists() else []

    def create_backup(self) -> Path:
        return self._backup_before_write()

    @staticmethod
    def _validated_project(payload: dict) -> str:
        name = payload.get("name", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("project name is required")
        return name.strip()

    def add_project(self, payload: dict) -> dict:
        name = self._validated_project(payload)
        project = {"id": uuid.uuid4().hex[:10], "name": name, "created_at": now(), "updated_at": now()}
        with self.transaction() as connection:
            self._backup_before_write()
            connection.execute("INSERT INTO projects VALUES (:id, :name, :created_at, :updated_at)", project)
        return project

    @staticmethod
    def _validated_item(payload: dict, existing: dict | None = None) -> dict:
        title = payload.get("title", existing.get("title") if existing else "")
        item_type = payload.get("type", existing.get("type") if existing else "Task")
        description = payload.get("description", existing.get("description") if existing else "")
        parent_id = payload.get("parent_id", existing.get("parent_id") if existing else None)
        status = payload.get("status", existing.get("status", "open") if existing else "open")
        priority = payload.get("priority", existing.get("priority", "medium") if existing else "medium")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title is required")
        if not isinstance(item_type, str) or item_type not in TYPES:
            raise ValueError("type must be one of: " + ", ".join(TYPES))
        if not isinstance(description, str):
            raise ValueError("description must be text")
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError("status must be one of: " + ", ".join(STATUSES))
        if not isinstance(priority, str) or priority not in PRIORITIES:
            raise ValueError("priority must be one of: " + ", ".join(PRIORITIES))
        if parent_id == "":
            parent_id = None
        if parent_id is not None and not isinstance(parent_id, str):
            raise ValueError("parent_id must be a string or null")
        return {"title": title.strip(), "type": item_type, "description": description, "parent_id": parent_id, "status": status, "priority": priority}

    @staticmethod
    def _project(connection: sqlite3.Connection, project_id: str | None) -> dict:
        if project_id:
            project = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not project:
                raise ValueError("project_id does not exist")
            return dict(project)
        project = connection.execute("SELECT * FROM projects ORDER BY created_at LIMIT 1").fetchone()
        if project:
            return dict(project)
        project = {"id": uuid.uuid4().hex[:10], "name": "General", "created_at": now(), "updated_at": now()}
        connection.execute("INSERT INTO projects VALUES (:id, :name, :created_at, :updated_at)", project)
        return project

    def add(self, payload: dict) -> dict:
        fields = self._validated_item(payload)
        with self.transaction() as connection:
            project = self._project(connection, payload.get("project_id"))
            if fields["parent_id"]:
                parent = connection.execute("SELECT project_id FROM items WHERE id = ?", (fields["parent_id"],)).fetchone()
                if not parent:
                    raise ValueError("parent_id does not exist")
                if parent["project_id"] != project["id"]:
                    raise ValueError("parent_id must be in the same project")
            item = {"id": uuid.uuid4().hex[:10], **fields, "project_id": project["id"], "created_at": now(), "updated_at": now()}
            self._backup_before_write()
            connection.execute(
                "INSERT INTO items VALUES (:id, :title, :type, :description, :parent_id, :project_id, :status, :priority, :created_at, :updated_at)", item
            )
        return item

    def update(self, item_id: str, payload: dict) -> dict:
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if not row:
                raise KeyError("item not found")
            item = dict(row)
            fields = self._validated_item(payload, item)
            if fields["parent_id"]:
                parent = connection.execute("SELECT project_id FROM items WHERE id = ?", (fields["parent_id"],)).fetchone()
                if not parent:
                    raise ValueError("parent_id does not exist")
                if parent["project_id"] != item["project_id"]:
                    raise ValueError("parent_id must be in the same project")
                current = fields["parent_id"]
                while current:
                    if current == item_id:
                        raise ValueError("an item cannot be its own ancestor")
                    parent_row = connection.execute("SELECT parent_id FROM items WHERE id = ?", (current,)).fetchone()
                    current = parent_row["parent_id"] if parent_row else None
            item.update(fields, updated_at=now())
            self._backup_before_write()
            connection.execute(
                "UPDATE items SET title=:title, type=:type, description=:description, parent_id=:parent_id, status=:status, priority=:priority, updated_at=:updated_at WHERE id=:id", item
            )
        return item


class Handler(SimpleHTTPRequestHandler):
    store: Store

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        print("web:", fmt % args)

    def send_json(self, status: int, body) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def body(self) -> dict:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Content-Length must be a number") from error
        if size < 1 or size > 65_536:
            raise ValueError("request body must be JSON and at most 65536 bytes")
        try:
            payload = json.loads(self.rfile.read(size))
        except json.JSONDecodeError as error:
            raise ValueError("request body must be JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/projects":
            self.send_json(HTTPStatus.OK, self.store.projects())
            return
        if parsed.path == "/api/items":
            self.send_json(HTTPStatus.OK, self.store.items(parse_qs(parsed.query).get("project", [None])[0]))
            return
        if parsed.path.startswith("/api/items/") and parsed.path[len("/api/items/"):]:
            try:
                self.send_json(HTTPStatus.OK, self.store.item(parsed.path[len("/api/items/"):]))
            except KeyError as error:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
            return
        if self.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/projects":
                self.send_json(HTTPStatus.CREATED, self.store.add_project(self.body()))
            elif path == "/api/items":
                self.send_json(HTTPStatus.CREATED, self.store.add(self.body()))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def do_PATCH(self):
        prefix = "/api/items/"
        path = urlparse(self.path).path
        if not path.startswith(prefix) or not path[len(prefix):]:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            self.send_json(HTTPStatus.OK, self.store.update(path[len(prefix):], self.body()))
        except KeyError as error:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


def run_server(host: str, port: int) -> None:
    Handler.store = Store(data_path())
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Work Items running at http://{host}:{port} (data: {Handler.store.path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


def cli_add(args: argparse.Namespace) -> None:
    payload = {"title": args.title, "type": args.type, "parent_id": args.parent, "project_id": args.project, "status": args.status, "priority": args.priority, "description": args.description}
    url = configured_url()
    item = remote_request(url, "/api/items", "POST", payload) if url else Store(data_path()).add(payload)
    print(json.dumps(item, indent=2))


def cli_list(args: argparse.Namespace) -> None:
    url = configured_url()
    items = remote_request(url, "/api/items") if url else Store(data_path()).items()
    if args.project is not None:
        items = [item for item in items if item.get("project_id") == args.project]
    if args.parent is not None:
        items = [item for item in items if item.get("parent_id") == args.parent]
    print(json.dumps(items, indent=2))


def cli_get(args: argparse.Namespace) -> None:
    reference = urlparse(args.item)
    item_id = args.item
    url = configured_url()
    if reference.scheme:
        item_id = parse_qs(reference.query).get("item", [""])[0]
        url = f"{reference.scheme}://{reference.netloc}"
    if not item_id:
        raise ValueError("item reference must be an item ID or a URL containing ?item=ITEM_ID")
    item = remote_request(url, f"/api/items/{item_id}") if url else Store(data_path()).item(item_id)
    print(json.dumps(item, indent=2))


def cli_project(args: argparse.Namespace) -> None:
    url = configured_url()
    if args.project_command == "list":
        projects = remote_request(url, "/api/projects") if url else Store(data_path()).projects()
        print(json.dumps(projects, indent=2))
    else:
        payload = {"name": args.name}
        project = remote_request(url, "/api/projects", "POST", payload) if url else Store(data_path()).add_project(payload)
        print(json.dumps(project, indent=2))


def cli_backup(args: argparse.Namespace) -> None:
    if configured_url():
        raise ValueError("Backups are local to the daemon host; run this command there")
    store = Store(data_path())
    if args.backup_command == "create":
        print(store.create_backup())
    else:
        print(json.dumps(store.backup_list(), indent=2))


def cli_open(args: argparse.Namespace) -> None:
    url = configured_url_for(args.url) if args.url else configured_url()
    url = url or f"http://127.0.0.1:{args.port}"
    webbrowser.open(url)
    print(f"Opened {url}")


def cli_config(args: argparse.Namespace) -> None:
    if args.config_command == "show":
        print(json.dumps({"url": configured_url(), "path": str(config_path())}, indent=2))
    elif args.config_command == "set-url":
        url = configured_url_for(args.url)
        config_path().parent.mkdir(parents=True, exist_ok=True)
        config_path().write_text(json.dumps({"url": url}, indent=2) + "\n")
        print(f"Configured CLI server: {url}")
    else:
        config_path().unlink(missing_ok=True)
        print("CLI server configuration cleared")


def check() -> None:
    """Fast self-check for SQLite persistence, backups, projects, and hierarchy safety."""
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "items.db")
        alpha = store.add_project({"name": "Alpha"})
        beta = store.add_project({"name": "Beta"})
        epic = store.add({"title": "Roadmap", "type": "Epic", "project_id": alpha["id"], "status": "inprogress", "priority": "high", "description": ""})
        task = store.add({"title": "Ship", "type": "Task", "project_id": alpha["id"], "parent_id": epic["id"], "description": ""})
        assert store.items(alpha["id"])[1]["parent_id"] == epic["id"]
        assert epic["status"] == "inprogress" and epic["priority"] == "high"
        assert store.backup_list()
        try:
            store.add({"title": "Wrong project", "type": "Task", "project_id": beta["id"], "parent_id": epic["id"], "description": ""})
        except ValueError as error:
            assert "same project" in str(error)
        else:
            raise AssertionError("cross-project parent accepted")
        try:
            store.update(epic["id"], {"parent_id": task["id"]})
        except ValueError as error:
            assert "ancestor" in str(error)
        else:
            raise AssertionError("cycle accepted")
        legacy = Path(directory) / "legacy"
        legacy.mkdir()
        (legacy / "items.json").write_text('[{"id":"child","title":"Child","type":"Task","description":"","parent_id":"parent","created_at":"x","updated_at":"x"},{"id":"parent","title":"Parent","type":"Epic","description":"","parent_id":null,"created_at":"x","updated_at":"x"}]')
        migrated = Store(legacy / "items.db")
        assert migrated.items()[0]["parent_id"] == "parent" and (legacy / "items.json").exists()
    print("check passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-first work-item manager")
    sub = parser.add_subparsers(dest="command", required=True)
    daemon = sub.add_parser("daemon", aliases=["serve"], help="host the web UI and API together")
    daemon.add_argument("--host", default="127.0.0.1")
    daemon.add_argument("--port", type=int, default=37481)
    open_web = sub.add_parser("open", help="open the configured web UI in a browser")
    open_web.add_argument("--url", help="open this URL instead of the configured server")
    open_web.add_argument("--port", type=int, default=37481, help="local daemon port when no URL is configured")
    add = sub.add_parser("add", help="create an item")
    add.add_argument("title")
    add.add_argument("--type", choices=TYPES, default="Task")
    add.add_argument("--project", help="project ID (defaults to the first or General project)")
    add.add_argument("--parent", help="parent item ID in the same project")
    add.add_argument("--status", choices=STATUSES, default="open")
    add.add_argument("--priority", choices=PRIORITIES, default="medium")
    add.add_argument("--description", default="")
    listing = sub.add_parser("list", help="print stored items as JSON")
    listing.add_argument("--project", help="only items in this project")
    listing.add_argument("--parent", help="only items with this parent ID")
    get = sub.add_parser("get", help="print one item from its ID or share URL")
    get.add_argument("item", help="item ID or URL containing ?item=ITEM_ID")
    project = sub.add_parser("project", help="create or query projects")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_sub.add_parser("list", help="print projects as JSON")
    project_add = project_sub.add_parser("add", help="create a project")
    project_add.add_argument("name")
    backup = sub.add_parser("backup", help="create or list local SQLite backups")
    backup_sub = backup.add_subparsers(dest="backup_command", required=True)
    backup_sub.add_parser("create", help="create a SQLite snapshot now")
    backup_sub.add_parser("list", help="list local SQLite snapshots")
    config = sub.add_parser("config", help="configure a remote API server for this CLI")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("show", help="show the configured server URL")
    set_url = config_sub.add_parser("set-url", help="save a remote server URL for this device")
    set_url.add_argument("url", help="for example http://work-items.local:37481")
    config_sub.add_parser("clear-url", help="return this CLI to its local SQLite store")
    sub.add_parser("check", help="run the built-in persistence check")
    args = parser.parse_args()
    if args.command in ("daemon", "serve"):
        run_server(args.host, args.port)
    elif args.command == "open":
        cli_open(args)
    elif args.command == "add":
        cli_add(args)
    elif args.command == "list":
        cli_list(args)
    elif args.command == "get":
        cli_get(args)
    elif args.command == "project":
        cli_project(args)
    elif args.command == "backup":
        cli_backup(args)
    elif args.command == "config":
        cli_config(args)
    else:
        check()


if __name__ == "__main__":
    main()
