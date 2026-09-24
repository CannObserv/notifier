# SocratiCode's shared store

Detail for [SOCRATICODE.md](../SOCRATICODE.md): where this repo's index lives,
how a session reaches it, and what `includeLinked` does and does not span.

## The shared store

A fifth cohort VM, `co-index`, runs the shared SocratiCode store (#57). **No
production path touches it**: its outage degrades search to `grep` and stops
no service. It checks in to a dead-man's timer here like any other consumer.

Stood up in #57. Everything persisted lives in Qdrant on `co-index` — chunks,
the dependency graph, the symbol graph and the context artifacts alike.
**Nothing is on this disk**, so a lost VM loses no index, which is the whole
point: the last per-VM install vanished for nine days and only a log noticed.

Configuration is the `env` block in `.claude/settings.json`, with
`QDRANT_API_KEY` in the git-ignored `.claude/settings.local.json`. Four things
about it are easy to get wrong and expensive to debug:

- **`QDRANT_URL` must be the full MagicDNS name**,
  `https://index.taild0fb76.ts.net:6333`. The certificate's SAN does not carry
  the short name, so `https://index:6333` fails verification.
- **TLS is mandatory, not decoration.** SocratiCode refuses to send
  `QDRANT_API_KEY` to a non-HTTPS, non-localhost host. Plain HTTP is not a
  degraded mode here; it is a refusal.
- **The `env` block applies only after the folder is trusted.** Until then
  `QDRANT_MODE` falls back to `managed` and SocratiCode tries to start **Docker
  containers** on a host that has none, rather than reporting a missing
  configuration.
- **`QDRANT_COLLECTION_PREFIX` and `SOCRATICODE_BRANCH_AWARE` must stay
  unset.** The first splits the cohort namespace including the global metadata
  collection; the second gives every branch its own six collections.
  `tests/deploy/test_socraticode_config.py` asserts both — on a bool rather than
  on the file it read, because two of the six files it opens hold secrets and
  pytest prints an assertion's operands in full under `-vv` (#73).
- **`.claude/settings.local.json` must stay untracked *and* ignored.** The same
  test file pins both, because neither check sees the other's state: `git
  check-ignore --no-index` exits 0 for a path `git add -f` has already staged,
  and without the flag it reports a tracked path as merely un-ignored, which
  sends the operator to `.gitignore` when the remedy is a key rotation. The rule
  was simply absent in broker, a public repo, and read as true for months (#68).

### Cross-repo search

`codebase_search` with **`includeLinked: true`** spans the cohort; it defaults
to false, so it must be named. A sibling's path must exist on disk even though
the data is remote.

**Those siblings are link stubs, not clones.** `resolveLinkedCollections` uses a
linked path for exactly two things — `effectiveBaseProjectId(path)` to name the
collection and `path.basename(path)` as a display label — and
`searchMultipleCollections` receives only `{name, label}`. No path reaches the
query; content comes wholly from Qdrant. So all four siblings on this VM —
`../archiver`, `../broker`, `../replicator`, `../watcher` — each hold one
`.socraticode.json` naming a `projectId`, plus a README saying why.

A stub is also what keeps each sibling indexed from its own VM (#63): a clone
here could be re-indexed by anything running on this host, and D11's lock is
host-local, so a shared Qdrant gives two hosts nothing to contend on. A
directory with no source cannot be indexed.

Verified 2026-09-13 by moving `../broker`, then a real clone, aside and
replacing it with a single 30-byte `.socraticode.json`: search returned broker
source with correct paths and line numbers, zero bytes of it on disk.

A stub also cannot drift. A real checkout carries the sibling's own
`.socraticode.json`, so a `projectId` change upstream leaves a stale clone
resolving to the old collection.

**Two silences stack here, and neither reaches the tool result.** A missing
directory is dropped by `loadLinkedProjects`'s `fs.existsSync` filter; a stub
naming a collection that does not exist yet is caught per-collection by
`searchMultipleCollections` and skipped with a `logger.warn` to stderr. Search
succeeds either way. **A green cross-repo result is not evidence that every
sibling answered**: each contributes only once its own repo has indexed
(#57 Phase 7).

**It reaches `codebase_search` and nothing else.** `codebase_impact`,
`codebase_graph_query`, `codebase_flow` and `codebase_context_search` are
single-project however many repos the store holds. The honest claim is
cross-repo *semantic code search*, never cross-repo impact analysis.

**Do not compare scores across the two modes.** A linked search ranks by raw
cosine so results from different collections can be ordered against each other;
an unlinked one returns the single-collection hybrid score. The numbers are on
different scales.
