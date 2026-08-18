# m5mgr

Run management for [gem5](https://www.gem5.org/): execute gem5, ingest the
resulting `m5out` directory (stats + config) into a SQLite database, and
query/filter/compare runs by id or name — via CLI or a small read-only web
dashboard.

## Install

```sh
pip install -e ".[dev]"
```

## Environment variables

See [SETUP.md](SETUP.md) for a step-by-step guide to setting these up,
including a per-project setup with direnv.

- `GEM5_BIN` — path to the gem5 executable. Required for `m5mgr run`.
- `M5MGR_HOME` — where the database and managed run store live. Defaults to
  `~/.local/share/m5mgr`.
- `M5MGR_SCOPE` — isolates runs into a separate database + run store within
  `M5MGR_HOME`, so multiple projects using m5mgr don't collide (shared run
  names/ids, mixed `list` output, etc.). Defaults to `default`. Only letters,
  digits, `_`, `-` and `.` are allowed. Typically set per-project, e.g. in
  that project's `.envrc`:

  ```sh
  export M5MGR_SCOPE=my-project
  ```

  Each scope gets its own `M5MGR_HOME/<scope>/m5mgr.db` and
  `M5MGR_HOME/<scope>/runs/`.

## Usage

```sh
export GEM5_BIN=/path/to/gem5.opt

# Run gem5, passing everything after `--` through unmodified.
# m5mgr injects its own -d <dir> so it always knows where the m5out lands.
m5mgr run --name my-experiment -- -re configs/my_config.py --some-flag=1

# Ingest a pre-existing m5out directory without invoking gem5 (e.g. the
# example directories under input/):
m5mgr import input/m5out_rtl3_32x32_single --name baseline

# List, filter, inspect, compare.
m5mgr list --stat 'system.cpu.ipc>1.0'
m5mgr show baseline --stat 'system.cpu.*'
m5mgr compare baseline my-experiment --stat 'system.cpu.*'

# Read-only web dashboard.
m5mgr web
```

Every run gets a name (yours) and a generated, sortable id (printed at the
end, e.g. `20260818T231955Z-4TZK9P`). Reference a run later by its id, an
unambiguous id prefix, or its name (name lookups error out if more than one
run shares that name — pass the id instead).

## Commands

| Command | Purpose |
|---|---|
| `run` | Execute gem5 (`--name`, `--outdir`, `--tag`, `--notes`, then `-- <gem5 args>`) |
| `import` | Ingest an existing m5out dir without running gem5 |
| `list` | List/filter runs by name, tag, stat value, or config param |
| `show` | Print stats/params for one run |
| `compare` | Side-by-side comparison (with delta/%-change for 2 runs) across runs |
| `rm` | Delete a run (DB record + optionally its files) |
| `web` | Start the read-only Flask dashboard |

Run `m5mgr <command> --help` for full flag details.

## Data model

Each run's `stats.txt` may contain more than one dump (gem5 writes a new
block on every stat dump/reset). `show`/`compare` default to the **last**
dump; pass `--dump N` or `--all-dumps` to see others.

`config.json` is flattened into dotted/bracketed parameter paths
(`system.cpu.numThreads`, `system.mem_ranges[0]`, ...) so runs can be
filtered by their simulated configuration, not just their results.

## Testing

```sh
pytest
```

Tests run against the example `m5out` directories in `input/` (including
multi-dump stats.txt files) and a fake gem5 stand-in
(`tests/fixtures/fake_gem5.sh`) — no real gem5 binary is required to run the
test suite. The actual `gem5` subprocess execution in `run` can only be
verified against a real gem5 binary outside this test suite.
