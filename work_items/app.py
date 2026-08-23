#!/usr/bin/env python3
"""A tiny local-first work-item server and CLI. Requires Python 3.10+."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
import threading
import uuid
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
TYPES = ("Epic", "Feature", "Task", "Bug")


def data_path() -> Path:
    default = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "work-items" / "items.json"
    return Path(os.environ.get("WORK_ITEMS_DATA", default))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def config_path() -> Path:
    return Path(os.environ.get("WORK_ITEMS_CONFIG", Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "work-items" / "config.json"))


def configured_url() -> str | None:
    """An environment variable wins, so automation need not alter a user's config."""
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
    """Small JSON store; one locked, atomically replaced file contains projects and items."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, open(str(self.path) + ".lock", "a") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

    def _state(self) -> dict:
        if not self.path.exists():
            return {"projects": [], "items": []}
        try:
            data = json.loads(self.path.read_text())
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid data file: {self.path}") from error
        # v0.0.1 stored a bare item list. Read it as a General project until the next write.
        if isinstance(data, list):
            return {"projects": [{"id": "general", "name": "General", "created_at": now(), "updated_at": now()}], "items": [{**item, "project_id": item.get("project_id", "general")} for item in data]}
        if not isinstance(data, dict) or not isinstance(data.get("projects"), list) or not isinstance(data.get("items"), list):
            raise ValueError(f"Data file must contain projects and items: {self.path}")
        return data

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=self.path.parent, prefix=self.path.name + ".", delete=False) as temp:
            temp.write(json.dumps(state, indent=2) + "\n")
        Path(temp.name).replace(self.path)

    def projects(self) -> list[dict]:
        return self._state()["projects"]

    def items(self, project_id: str | None = None) -> list[dict]:
        items = self._state()["items"]
        return [item for item in items if item.get("project_id") == project_id] if project_id else items

    @staticmethod
    def _validated_project(payload: dict) -> str:
        name = payload.get("name", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("project name is required")
        return name.strip()

    def add_project(self, payload: dict) -> dict:
        with self.transaction():
            state = self._state()
            name = self._validated_project(payload)
            project = {"id": uuid.uuid4().hex[:10], "name": name, "created_at": now(), "updated_at": now()}
            state["projects"].append(project)
            self.save(state)
            return project

    @staticmethod
    def _validated_item(payload: dict, existing: dict | None = None) -> dict:
        title = payload.get("title", existing.get("title") if existing else "")
        item_type = payload.get("type", existing.get("type") if existing else "Task")
        description = payload.get("description", existing.get("description") if existing else "")
        parent_id = payload.get("parent_id", existing.get("parent_id") if existing else None)
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title is required")
        if not isinstance(item_type, str) or item_type not in TYPES:
            raise ValueError("type must be one of: " + ", ".join(TYPES))
        if not isinstance(description, str):
            raise ValueError("description must be text")
        if parent_id == "":
            parent_id = None
        if parent_id is not None and not isinstance(parent_id, str):
            raise ValueError("parent_id must be a string or null")
        return {"title": title.strip(), "type": item_type, "description": description, "parent_id": parent_id}

    @staticmethod
    def _descendant(items: list[dict], candidate_parent: str, item_id: str) -> bool:
        parents = {item["id"]: item.get("parent_id") for item in items}
        current = candidate_parent
        while current:
            if current == item_id:
                return True
            current = parents.get(current)
        return False

    @staticmethod
    def _project(state: dict, project_id: str | None) -> dict:
        if project_id:
            project = next((project for project in state["projects"] if project["id"] == project_id), None)
            if not project:
                raise ValueError("project_id does not exist")
            return project
        if state["projects"]:
            return state["projects"][0]
        project = {"id": uuid.uuid4().hex[:10], "name": "General", "created_at": now(), "updated_at": now()}
        state["projects"].append(project)
        return project

    def add(self, payload: dict) -> dict:
        with self.transaction():
            state = self._state()
            project = self._project(state, payload.get("project_id"))
            fields = self._validated_item(payload)
            if fields["parent_id"]:
                parent = next((item for item in state["items"] if item["id"] == fields["parent_id"]), None)
                if not parent:
                    raise ValueError("parent_id does not exist")
                if parent.get("project_id") != project["id"]:
                    raise ValueError("parent_id must be in the same project")
            item = {"id": uuid.uuid4().hex[:10], **fields, "project_id": project["id"], "created_at": now(), "updated_at": now()}
            state["items"].append(item)
            self.save(state)
            return item

    def update(self, item_id: str, payload: dict) -> dict:
        with self.transaction():
            state = self._state()
            item = next((item for item in state["items"] if item["id"] == item_id), None)
            if not item:
                raise KeyError("item not found")
            fields = self._validated_item(payload, item)
            parent_id = fields["parent_id"]
            if parent_id:
                parent = next((other for other in state["items"] if other["id"] == parent_id), None)
                if not parent:
                    raise ValueError("parent_id does not exist")
                if parent.get("project_id") != item.get("project_id"):
                    raise ValueError("parent_id must be in the same project")
                if self._descendant(state["items"], parent_id, item_id):
                    raise ValueError("an item cannot be its own ancestor")
            item.update(fields, updated_at=now())
            self.save(state)
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
        if size < 1:
            raise ValueError("request body must be JSON")
        if size > 65_536:
            raise ValueError("request body is too large")
        try:
            payload = json.loads(self.rfile.read(size))
        except json.JSONDecodeError as error:
            raise ValueError("request body must be JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/projects":
            try:
                self.send_json(HTTPStatus.OK, self.store.projects())
            except ValueError as error:
                self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
            return
        if path == "/api/items":
            try:
                project_id = None
                query = urlparse(self.path).query
                if query.startswith("project="):
                    project_id = query.removeprefix("project=")
                self.send_json(HTTPStatus.OK, self.store.items(project_id))
            except ValueError as error:
                self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
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
            status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE if "too large" in str(error) else HTTPStatus.BAD_REQUEST
            self.send_json(status, {"error": str(error)})

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
            status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE if "too large" in str(error) else HTTPStatus.BAD_REQUEST
            self.send_json(status, {"error": str(error)})


def run_server(host: str, port: int) -> None:
    Handler.store = Store(data_path())
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Work Items running at http://{host}:{port} (data: {data_path()})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


def cli_add(args: argparse.Namespace) -> None:
    payload = {"title": args.title, "type": args.type, "parent_id": args.parent, "project_id": args.project, "description": args.description}
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


def cli_project(args: argparse.Namespace) -> None:
    url = configured_url()
    if args.project_command == "list":
        projects = remote_request(url, "/api/projects") if url else Store(data_path()).projects()
        print(json.dumps(projects, indent=2))
    else:
        payload = {"name": args.name}
        project = remote_request(url, "/api/projects", "POST", payload) if url else Store(data_path()).add_project(payload)
        print(json.dumps(project, indent=2))


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
    """Fast self-check for persistence, projects, and tree safety."""
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "items.json")
        alpha = store.add_project({"name": "Alpha"})
        beta = store.add_project({"name": "Beta"})
        epic = store.add({"title": "Roadmap", "type": "Epic", "project_id": alpha["id"], "description": ""})
        task = store.add({"title": "Ship", "type": "Task", "project_id": alpha["id"], "parent_id": epic["id"], "description": ""})
        assert Store(store.path).items(alpha["id"])[1]["parent_id"] == epic["id"]
        assert not Store(store.path).items(beta["id"])
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
    add.add_argument("--description", default="")
    listing = sub.add_parser("list", help="print stored items as JSON")
    listing.add_argument("--project", help="only items in this project")
    listing.add_argument("--parent", help="only items with this parent ID")
    project = sub.add_parser("project", help="create or query projects")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_sub.add_parser("list", help="print projects as JSON")
    project_add = project_sub.add_parser("add", help="create a project")
    project_add.add_argument("name")
    config = sub.add_parser("config", help="configure a remote API server for this CLI")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("show", help="show the configured server URL")
    set_url = config_sub.add_parser("set-url", help="save a remote server URL for this device")
    set_url.add_argument("url", help="for example http://work-items.local:37481")
    config_sub.add_parser("clear-url", help="return this CLI to its local JSON store")
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
    elif args.command == "project":
        cli_project(args)
    elif args.command == "config":
        cli_config(args)
    else:
        check()


if __name__ == "__main__":
    main()
