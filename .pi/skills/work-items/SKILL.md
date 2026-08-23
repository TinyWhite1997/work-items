---
name: work-items
description: Safely operate this repository's local work-item CLI to create and query persisted Epic, Feature, Task, and Bug items. Use when managing this app's work items.
---

# Work Items CLI

Use the installed `work-items` executable; it shares the daemon's persisted store with the web UI.

## Safe workflow

1. Determine where the server runs. For a remote server, configure its HTTP URL on this client device first.
2. Query before choosing a parent: `work-items list`.
3. Create only with one of `Epic`, `Feature`, `Task`, or `Bug`.
4. Copy the exact parent `id` from JSON; never guess it.
5. Query again to verify the saved result.

```sh
# On the host, start one daemon for both UI and API.
work-items daemon --host 0.0.0.0 --port 37481

# One-time configuration on this CLI device. It persists locally.
work-items config set-url http://SERVER_IP:37481
work-items config show

# These calls now use the server API, not a local JSON file.
work-items list
work-items add "Release 1" --type Epic --description "Concise outcome"
work-items add "Nested work" --type Task --parent PARENT_ID
work-items list --parent PARENT_ID

# Open the configured server's web UI.
work-items open

# For one command/script only, without changing configuration:
WORK_ITEMS_URL=http://SERVER_IP:37481 work-items list
```

`work-items config clear-url` returns the CLI to its local data file. Do not edit the server's JSON file directly. The remote API validates parent IDs and prevents hierarchy cycles; report its error instead of bypassing it. This first release has no authentication, so only use a trusted LAN or protected network.
