# Work Items

A self-hosted, local-first work-item manager. It uses Python's standard library and stores data in `~/.local/share/work-items/items.json` (or `WORK_ITEMS_DATA`), so the browser and CLI always use the same file.

## Install and run

```sh
python3 -m pip install .

# One local daemon serves both the compiled web UI and its API.
work-items daemon
work-items open
# opens http://127.0.0.1:37481
```

The install creates the `work-items` executable. The packaged `work_items/web/` build is served directly. The UI is a shadcn/ui + React frontend with a nested tree, icon-coded Epic/Feature/Task/Bug rows, and a responsive detail sheet. **Expand details** widens the sheet; **Return to tree** restores the split view.

### Change the UI

```sh
cd ui
npm install
npm run build       # writes the packaged frontend to ../work_items/web/
# optional during development, with the daemon already running:
npm run dev
```

The Vite development server proxies `/api` to `http://127.0.0.1:37481`; start `work-items daemon` (or `python3 app.py daemon` in a checkout) first.

## CLI

By default, the CLI reads the local `data/items.json`. Configure a URL once on every client device to have `add` and `list` use a server's HTTP API instead.

```sh
# On the host machine: one daemon binds the web UI and API to its LAN interface.
work-items daemon --host 0.0.0.0 --port 37481

# On each client machine: save that host's reachable address.
work-items config set-url http://SERVER_IP:37481
work-items config show

# These now use the remote server's persisted store.
work-items add "Release 1" --type Epic --description "First local release"
work-items list
work-items add "Core UI" --type Feature --parent EPIC_ID
work-items list --parent EPIC_ID

# Return this CLI to its local JSON store.
work-items config clear-url
```

The URL is stored in `~/.config/work-items/config.json` (override with `WORK_ITEMS_CONFIG`). `WORK_ITEMS_URL=http://SERVER_IP:37481` temporarily overrides it, useful for scripts. Output is JSON, including the generated `id`. Types must be `Epic`, `Feature`, `Task`, or `Bug`.

The first release has no authentication: expose `0.0.0.0` only on a trusted LAN or behind your own network protection.

## Checks

```sh
work-items check
```

The check verifies durable hierarchy persistence and rejects parent-child cycles.
