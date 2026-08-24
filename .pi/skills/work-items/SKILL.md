---
name: work-items
description: Operate the Work Items CLI to create, inspect, and organize local or remote Epic, Feature, Task, and Bug items. Use this skill whenever a user asks to manage work items, create nested work, query a work-item store, configure a Work Items server, or use the `work-items` command.
compatibility: Requires the `work-items` executable from TinyWhite1997/work-items and Python 3.10+.
---

# Work Items CLI

Use the installed `work-items` command. It operates the same persisted store as the Work Items web UI.

## Safe workflow

1. Start with `work-items config show` and `work-items project list`.
2. Create a project or copy its exact `id` before adding project work.
3. Before adding a child, copy the exact parent `id` from `work-items list --project PROJECT_ID`; do not guess IDs.
4. Create only `Epic`, `Feature`, `Task`, or `Bug` items.
5. Set status to `open`, `inprogress`, `closed`, `resolved`, or `blocked`, and priority to `low`, `medium`, `high`, or `urgent` when the user supplies them; otherwise accept the CLI defaults (`open`, `medium`).
6. Query again after a mutation and report the created item ID.
7. Never edit the SQLite database directly. The CLI/API owns validation, transactions, and automatic pre-write backups.

```sh
work-items config show
work-items project add "Website"
work-items project list
work-items add "Release 1" --type Epic --project PROJECT_ID --status inprogress --priority high --description "Concise outcome"
work-items add "Nested work" --type Task --project PROJECT_ID --parent PARENT_ID --status open --priority medium
work-items list --project PROJECT_ID --parent PARENT_ID
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

Use `work-items config clear-url` to return the client to local SQLite storage. On the daemon host, use `work-items backup list` to inspect automatic SQLite snapshots or `work-items backup create` to create one before a high-risk change.

## Hosting

`work-items daemon` serves the packaged web UI and API together on `127.0.0.1:37481` by default. Use `work-items daemon --host 0.0.0.0` only when the user explicitly wants LAN access: this first release has no authentication.
