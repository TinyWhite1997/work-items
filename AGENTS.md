# Work Items

Build the product requested by the user. Keep the first release deliberately small and end-to-end.

## Non-negotiable acceptance

- Tree-first work-item UI: children are nested in the left list.
- Selecting an item opens a right-side detail drawer; expanding it covers the tree while preserving a way back.
- Desktop and mobile are both usable.
- Supported item types have distinct icons: Epic, Feature, Task, Bug (at minimum).
- Browser UI can create, edit, and display items correctly.
- A CLI can create and query the same persisted data; its changes sync with the web UI after refresh/reload.
- Provide a Pi skill so AI agents can operate the same CLI safely.
- Final acceptance must use `agent-browser` to test desktop and mobile browser flows, plus real CLI commands. Do not call the goal complete without that evidence.

## Execution

Use the installed `pi-goal` extension for this mission. Use `pi-subagents` to delegate read-only research/review/validation or isolated work when useful, but retain one writer for the active checkout. Read the `ponytail` skill before choosing the stack and follow it: use the smallest boring implementation that satisfies the acceptance criteria. Do not add authentication, collaboration, cloud deployment, or speculative workflow engines.
