---
name: work-items
description: Operate the Work Items CLI to create, inspect, and organize local or remote Epic, Feature, Task, and Bug items. Use this skill whenever a user asks to manage work items, create nested work, query a work-item store, configure a Work Items server, or use the `work-items` command.
compatibility: Requires the `work-items` executable from TinyWhite1997/work-items and Python 3.10+.
---

# Work Items CLI

Use the installed `work-items` command. It operates the same persisted store as the Work Items web UI.

## Safe workflow

1. Start with `work-items config show` and `work-items list`.
2. Before adding a child, copy the exact parent `id` from `work-items list`; do not guess IDs.
3. Create only `Epic`, `Feature`, `Task`, or `Bug` items.
4. Query again after a mutation and report the created item ID.
5. Never edit the JSON data file directly. The CLI/API owns validation, locking, and atomic writes.

```sh
work-items config show
work-items list
work-items add "Release 1" --type Epic --description "Concise outcome"
work-items add "Nested work" --type Task --parent PARENT_ID
work-items list --parent PARENT_ID
```

## Remote server

A client uses its own saved server address. Configure it only when the user supplies or approves the endpoint:

```sh
work-items config set-url https://SERVER:37481
work-items config show
work-items open
```

For a one-command override that does not modify persistent configuration:

```sh
WORK_ITEMS_URL=https://SERVER:37481 work-items list
```

Use `work-items config clear-url` to return the client to local storage.

## Hosting

`work-items daemon` serves the packaged web UI and API together on `127.0.0.1:37481` by default. Use `work-items daemon --host 0.0.0.0` only when the user explicitly wants LAN access: this first release has no authentication.
