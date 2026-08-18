#!/usr/bin/env bash
# Stand-in "gem5" executable for runner tests - no real gem5 binary is
# available in this environment. Records the argv it received (for
# assertions on invocation shape) and writes a minimal synthetic m5out
# (stats.txt + config.json) into the directory passed via -d, so the
# post-run ingestion pipeline can be exercised too.
set -euo pipefail

argv_file="${FAKE_GEM5_ARGV_FILE:-}"
if [ -n "$argv_file" ]; then
  printf '%s\n' "$@" > "$argv_file"
fi

outdir=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "-d" ]; then
    outdir="$arg"
  fi
  prev="$arg"
done

if [ -z "$outdir" ]; then
  echo "fake_gem5: no -d <dir> found in args" >&2
  exit 1
fi

echo "fake_gem5: stdout hello"
echo "fake_gem5: stderr hello" >&2

mkdir -p "$outdir"

cat > "$outdir/stats.txt" <<'EOF'
---------- Begin Simulation Statistics ----------
simSeconds                                   0.001000                       # Number of seconds simulated (Second)
simTicks                                   1000000000                       # Number of ticks simulated (Tick)

---------- End Simulation Statistics   ----------
EOF

cat > "$outdir/config.json" <<'EOF'
{"type": "Root", "name": null, "system": {"cpu": {"numThreads": 1}}}
EOF

exit "${FAKE_GEM5_EXIT_CODE:-0}"
