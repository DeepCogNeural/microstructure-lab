#!/usr/bin/env bash
# Explicit command, separate run log and exit receipt; never reuse a run ID.
set -eu
base="${MICROSTRUCTURE_ROOT:-$HOME/microstructure-compute}"
run="$1"
seconds="$2"
shift 2
case "$run" in *[!a-zA-Z0-9_-]*|'') exit 2;; esac
mkdir "$base/logs/$run"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export PYTHONPATH="$base/src/src"
cd "$base/src"
date -u +%FT%TZ > "$base/logs/$run/started_utc"
printf '%s\n' "$@" > "$base/logs/$run/command.txt"
set +e
timeout --signal=TERM --kill-after=30 "$seconds" "$@" > "$base/logs/$run/stdout.log" 2> "$base/logs/$run/stderr.log"
code=$?
printf '%s\n' "$code" > "$base/logs/$run/exit_code"
date -u +%FT%TZ > "$base/logs/$run/finished_utc"
exit "$code"
