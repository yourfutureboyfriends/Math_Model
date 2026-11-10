# Saved research layouts

Launchpad now supports up to 12 named local layouts, retaining the grid, functions, securities and colour links. Names are limited to 48 characters. Existing names are not overwritten silently. Browser-storage failures are reported without falsely claiming a save.

Restoring a saved layout, applying a research preset or resetting the layout provides a one-step undo. Removing a named layout provides a separate undo. Saved values are validated before rendering, including supported grid sizes, valid functions, supported colour groups and a six-pane limit. Recursive Launchpad panes are rejected.

Saved data is local to this browser and is not synchronized between users or devices. This stores layout configuration, not financial-model assumptions or captured market data.

Validation: two behavior tests pass, covering save/restore/remove/undo and malformed saved data. Browser visual review is not completed.
