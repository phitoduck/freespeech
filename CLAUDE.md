# Working in this repo

Only the things that have actually caught people out. Everything else is in
`docs/` or discoverable from the code.

## Node: the `pnpm` trap

The nvm default here is Node 22.10; pnpm 11 refuses to run on it and reports
something that reads like the toolchain is broken. Node 26.7.0 is installed
elsewhere. Prefix any direct `pnpm` call:

```bash
export PATH=/opt/homebrew/opt/node/bin:$PATH
```

The `Makefile` already does this, so `make test-ts` and `make lint` are safe.
An agent concluded "the TypeScript suite cannot run in this environment" after
skipping it; the suite runs fine and passes 13 tests.

## Servers

`make dev` runs the API on `:8000` and Vite on `:5173`.

- The API runs **without `--reload`** — restart it yourself after changing
  `apps/api/`, or you will test stale code and believe your fix failed.
- Do **not** kill servers you did not start. The end-to-end fixtures start
  their own API on a free port and reuse Vite on 5173 (its port is fixed by
  the CORS allow-list), so leaving 8000/5173 alone costs you nothing.
- Kokoro synthesis is genuinely multi-core. A test run at 500% CPU is working,
  not hung, and two concurrent suites will slow each other to the point where a
  timeout looks like a deadlock. Check elapsed time before killing anything.

## Tests

```bash
make test        # fast: no browser, no model
make test-all    # everything
make test-e2e    # browser scenarios; regenerates the docs screenshots
```

Markers: `docs` selects **browser** scenarios (it does not mean "emits an
image" — some deliberately produce none), `kokoro` selects the one test that
loads the real model. `make test` excludes both.

## Mutation testing

Deliberately breaking the implementation to prove a test fails is normal
practice here and several tests exist because of it. If you do it:

1. record `md5 -q <file>` first,
2. restore byte-for-byte,
3. confirm the md5 matches before you finish.

A mutation left in `apps/` is the worst thing you can leave behind, because
everything still looks green locally.

## One habit worth keeping

A green test, an empty `grep`, or "no results" is evidence only once you have
shown the check *can* produce the opposite answer. Roughly half the defects
found in this project were checks that could not fail — see the table in
`.humanlayer/tasks/pdf-karaoke-reader/05-implementation.md`.

The commonest way to build one by accident is `2>/dev/null`. A command that
**errors** prints nothing on stdout and exits non-zero, which is
indistinguishable from a clean "nothing found" once stderr is discarded:

```bash
find docs -name '*.png' -newermt '-10 minutes' 2>/dev/null   # always empty here
```

`find` on this machine is `bfs`, which rejects relative timestamps — that line
reports "no files changed recently" no matter what changed. It was read as
proof that a subagent had stalled, and the agent was killed while it was
working. Never suppress stderr on a check whose *emptiness* you intend to treat
as a result; check the exit status, or run the negative control first.
