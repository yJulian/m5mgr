# Setup

m5mgr is configured entirely through environment variables. This document
explains what to set and how.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GEM5_BIN` | Yes, for `m5mgr run` | — | Path to the gem5 executable |
| `M5MGR_HOME` | No | `~/.local/share/m5mgr` | Where the database and run files are stored |
| `M5MGR_SCOPE` | No | `default` | Isolates runs per project/workspace |

### `GEM5_BIN`

Absolute path to the gem5 executable you want m5mgr to invoke. Only needed
for `m5mgr run` — not needed for `import`, `list`, `show`, `compare`, `rm`,
or `web`.

```sh
export GEM5_BIN=/home/julian/gem5/build/RISCV/gem5.opt
```

m5mgr checks that the path exists when `run` is invoked; if `GEM5_BIN` is
unset or points at a nonexistent file, `run` fails immediately with a clear
error instead of trying to execute anything.

### `M5MGR_HOME`

Root directory for everything m5mgr persists: the SQLite database(s) and the
copied `m5out` directories for each run. Created automatically if it doesn't
exist.

```sh
export M5MGR_HOME=/home/julian/.local/share/m5mgr   # default, shown explicitly
```

Point this somewhere else if you want m5mgr's data on a different disk (e.g.
a large scratch volume, since `m5out` directories can be sizable) or if you
want a fully separate m5mgr instance for some reason.

### `M5MGR_SCOPE`

Names the "workspace" m5mgr operates in. Everything — run ids, run names,
stats, config params — lives inside `M5MGR_HOME/<scope>/`. Two different
scopes never see each other's runs, even if they reuse the same run name.

```sh
export M5MGR_SCOPE=flexnngine2_rtl3
```

Use this to keep separate gem5 projects (different repos, different
research questions, different people) from cluttering each other's `m5mgr
list` output or colliding on run names. If unset, everything goes into the
`default` scope.

Allowed characters: letters, digits, `_`, `-`, `.` (no `/`, no spaces —
it becomes a directory name under `M5MGR_HOME`). An invalid value makes
every command fail with a clear error rather than silently falling back to
`default`.

Resulting layout for a scope named `my-project`:

```
M5MGR_HOME/
  my-project/
    m5mgr.db
    runs/
      <run-id>/
        m5out/
          stats.txt
          config.json
          ...
```

## Setting env vars

### One-off, current shell session

```sh
export GEM5_BIN=/path/to/gem5.opt
export M5MGR_SCOPE=my-project
```

These only last for the current terminal session.

### Persistently, for every shell

Add the `export` lines to your shell's startup file:

- bash: `~/.bashrc`
- zsh: `~/.zshrc`

```sh
echo 'export GEM5_BIN=/path/to/gem5.opt' >> ~/.bashrc
```

Reasonable for `GEM5_BIN` and `M5MGR_HOME` if you mostly work with one gem5
build. Less useful for `M5MGR_SCOPE` if you switch between projects often —
see below instead.

### Per-project, automatically (recommended for `M5MGR_SCOPE`)

If you use [direnv](https://direnv.net/), drop a `.envrc` in each gem5
project's directory:

```sh
# .envrc in ~/projects/flexnngine2_rtl3/
export GEM5_BIN=/home/julian/gem5_cva6/build/RISCV/gem5.opt
export M5MGR_SCOPE=flexnngine2_rtl3
```

```sh
cd ~/projects/flexnngine2_rtl3
direnv allow
```

Now `GEM5_BIN` and `M5MGR_SCOPE` are set automatically whenever you `cd`
into that project, and unset again when you leave it — no risk of running
`m5mgr` in the wrong scope by mistake.

Without direnv, you can achieve the same thing with a small `source`-able
script per project:

```sh
# env.sh in your project
export GEM5_BIN=/home/julian/gem5_cva6/build/RISCV/gem5.opt
export M5MGR_SCOPE=flexnngine2_rtl3
```

```sh
source env.sh
m5mgr run --name my-experiment -- -re configs/my_config.py
```

## Verifying your setup

```sh
# Confirms GEM5_BIN resolves and M5MGR_SCOPE/M5MGR_HOME are valid.
m5mgr list
```

`m5mgr list` prints the active scope at the top of its output (`Scope:
<name>`), so it's a quick way to confirm which workspace you're about to
operate in before running or deleting anything.
