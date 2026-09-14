# Public contribution and privacy policy

This is a public research repository. Every commit must be safe to publish.

## Hard privacy gate

Never commit any of the following:

- hostnames, server/cluster names, internal domains, IP addresses, SSH targets, or mount points;
- CPU/GPU model inventory, per-host RAM/core counts, device UUIDs, driver inventory, or scheduler allocation/job IDs tied to private infrastructure;
- absolute home-directory paths, usernames, environment dumps, shell history, credentials, tokens, keys, or connection details;
- internal application strategy, recruiter-specific notes, advisor reviews, agent handoff/completion receipts, or private workflow instructions;
- raw licensed market data, row-level derived market data, row-level predictions, model binaries, or large execution logs.

Public engineering evidence should be infrastructure-neutral: algorithms, tests, scientific configuration, aggregate metrics, hashes, and aggregate performance ratios are appropriate.

## Automation / agent rule

Any automated coding agent working in this repository must apply this file as a hard pre-push gate. If a requested artifact contains private infrastructure or application-process details, keep it outside the public repository.

Before pushing, inspect the diff and repository search results for accidental infrastructure metadata. Environment capture used for local reproducibility must remain local and must not be copied into committed CSV/JSON/Markdown artifacts.

## Scientific claim boundary

- Do not claim realized PnL from midpoint markouts.
- Do not treat overlapping row counts as IID statistical evidence.
- Do not claim a universal model winner from a bounded benchmark.
- Keep train/test chronology and negative controls explicit.
- Report missing/failed tasks rather than silently excluding them.
- Do not change fixed test definitions after inspecting final-test quality without clearly starting a new experiment version.

## Public artifact checklist

A publishable experiment update should normally contain only:

1. source code and tests;
2. infrastructure-neutral scientific configuration;
3. dataset attribution/license evidence;
4. aggregate results and small plots;
5. a methods/results report with limitations;
6. no private execution metadata.
