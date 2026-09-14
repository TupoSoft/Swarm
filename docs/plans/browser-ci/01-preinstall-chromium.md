# Reuse Chromium from the Isolated Runner Image

This is a living ExecPlan maintained according to LeadEmailFinder's `.agents/PLANS.md`. It describes exactly
one pull request in `TupoSoft/Swarm`; all implementation paths below are relative to that repository.

## Purpose / Big Picture

Every fresh isolated worker will already contain the Chromium binaries and operating system libraries used
by LeadEmailFinder's locked Playwright version. Its existing browser installation command will reuse those
binaries. A developer can prove this by starting a fresh worker image without network access and using the
same Playwright version to install and launch Chromium without downloading a browser.

This removes repeated browser downloads and library installation from the browser job. The existing
`--with-deps` command still checks operating system packages, so a zero-duration setup step is not promised.
The change does not establish that the entire browser workflow fits its current timeout.

## Progress

- [x] (2026-09-14) Bake Chromium and its system libraries into the existing worker image.
- [x] (2026-09-14) Add checks for installation reuse, browser launch, permissions, and fresh worker state.
- [x] (2026-09-14) Run local validation and document the image publication and operational verification procedure.
- [x] (2026-09-14) Move provisioning into `install-chromium.cjs`, separate the offline Docker build steps, and
  repeat focused validation for the readability refactor at commit `a5b8a9c`. These are historical JavaScript
  results; the first three progress items describe the initial implementation at commit `f8d4282`.
- [x] (2026-09-14) Replace the provisioning script with `install-chromium.sh` as requested, validate POSIX shell
  syntax and failure handling, and repeat the focused image and runtime checks at commit `df33322`.
- [x] (2026-09-14) Add Node and npm, install pinned Playwright globally, remove custom archive and metadata
  handling, and validate the simplified installation and retained tools in fresh containers.

## Plan dependencies

None.

## Surprises & Discoveries

- (2026-09-14, before the readability refactor) Two fresh final-image containers reused and launched both browser
  modes offline. The existing installer flags completed in 9.10 seconds locally with zero browser downloads and
  zero newly installed packages;
  package index retrieval remained. This is local evidence, not a deployed CI timing improvement.
- (2026-09-14) Harper dependencies are absent from this task directory. The repository lint command ran from
  the main LeadEmailFinder directory against both absolute paths in this Swarm worktree.
- (2026-09-13) The launcher mounts only the workspace and private socket into workers. `/home/runner` is fresh
  image filesystem state, not a mounted home volume. An image path outside the workspace survives its mount.
- (2026-09-13) Stack environment variables do not automatically reach workers. The launcher explicitly passes
  registration and runner settings, so the browser location must be defined with `ENV` in the Dockerfile.
- (2026-09-13, before global installation was authorized) The image had runner-provided Node executables but
  no global Node package manager.
  `playwright-core@1.63.0` has no runtime package dependencies and supports Node 20 or later. Its checked archive
  can run directly with the runner's bundled Node 24 executable.
- (2026-09-13) Swarm PR #75 added `gh-actions-runner/tests/check_git_capabilities.py` and runs it during the
  image build. Preserve that existing Git capability check when adding the browser check.

## Decision Log

- Decision: Extend the existing Ubuntu 22.04 isolated runner image.
  Rationale: The private daemon, matching workspace mounts, localhost ports, and ephemeral worker lifecycle are
  existing contracts. Browser provisioning does not require changing those contracts or replacing the base image.
  Date/Author: 2026-09-13, Codex planning.
- Decision: Use image-level `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` and make that directory writable by `runner`.
  Rationale: The path is outside the shared workspace. Each job writes only its own disposable container layer,
  including package links and any different browser version requested by another repository.
  Date/Author: 2026-09-13, Codex planning.
- Decision: Preserve LeadEmailFinder's existing `playwright install --with-deps chromium` command.
  Rationale: Matching versions reuse the installed binaries, while different locked versions retain the existing
  installation behavior. Deployment needs no coordinated consumer change or new scheduling label.
  Date/Author: 2026-09-13, Codex planning.
- Decision: Use `gh-actions-runner/install-chromium.sh` with `#!/bin/sh` and `set -eu` for browser provisioning.
  Rationale: The user requested POSIX shell. Keep installation in this short script and give offline reuse and
  browser launch their own Dockerfile instructions.
  Date/Author: 2026-09-14, Codex implementation following the user's POSIX shell request.
- Decision: Copy Node 24 and npm from `node:24-bookworm-slim`, install `playwright@1.63.0` globally with npm,
  and retain those tools in the final image. npm owns registry downloads and package integrity verification.
  Rationale: The user authorized npm and global Playwright to simplify installation. This supersedes the earlier
  exclusions of global Node and Playwright and requirements for custom archive verification and diagnostic metadata.
  Remove `PLAYWRIGHT_INTEGRITY` and the custom manifest. Keep the pinned Playwright version, browser path,
  POSIX script, offline checks, and consumer lockfile behavior.
  Date/Author: 2026-09-14, Codex implementation following the user's global installation request.

## Outcomes & Retrospective

Draft PR #76 now uses npm to install pinned Playwright globally and provision its Chromium assets and Linux
libraries. The image exposes the browser path to workers and retains Node, npm, `npx`, and Playwright on `PATH`.
The image build and two fresh worker checks passed, proving offline installation reuse, the pinned package
version, and both Chromium launch modes as `runner`. The 20 existing tests, POSIX shell checks, rejection checks,
and documentation lint also passed. Independent review found no actionable issues or material SOLID trade-offs.

The earlier implementations at `f8d4282`, `a5b8a9c`, and `df33322` passed their focused local checks. Their
historical evidence is recorded separately below. The consuming workflow
and runner resource settings remain unchanged.

The PR image build must pass before image publication. Image publication, deployment, and a measured setup-time
improvement on the Swarm pool remain separate operational work; none is claimed by these local results.

## Context and Orientation

Before implementation, at Swarm commit `47c193f1b43cd1e6283b23dde5924a1495c7da56`, the Dockerfile built Ubuntu 22.04
with Actions runner `2.337.0`, Docker tooling, and general compilation libraries. It installed no Chromium.
`gh-actions-runner/entrypoint.sh` is the trusted launcher. It creates one worker and one private Docker daemon,
then removes that pair and its owned volumes after the job. `gh-actions-runner/runner-entrypoint.sh` configures
the worker, exports temporary paths in the workspace, removes its registration token, and runs jobs as `runner`.

The workspace volume covers `/actions-runner/_work`; a separate private socket volume covers `/var/run`.
The worker receives neither the Swarm host socket nor the organization personal access token. Each worker and
daemon retains its current limit of two CPUs and `4g` memory. Two launcher replicas provide two job slots.

`.github/workflows/build-push.yml` builds the image on the existing runner pool for internal pull requests and
publishes `ghcr.io/tuposoft/gh-actions-runner:self-hosted-ci` from `master`. Its pull request path cannot publish.
The runner deployment workflow uses durable registry pull credentials and preserves both manual and daily
deployment triggers. Publication and an eventual deployment are separate from preparing this source change.

LeadEmailFinder's `pnpm-lock.yaml` at commit `43f1382876bbf40aac067a5fc57a5e3f08e3b05f` resolves Playwright to
`1.63.0`. Its browser job executes `playwright install --with-deps chromium` after dependency installation.
The package's browser manifest selects Chromium and Chromium Headless Shell revision `1243`, browser version
`153.0.8010.12`, plus FFmpeg revision `1011`. Use the package manifest through its CLI rather than hardcoding
binary directory names. Playwright documents version-specific browser binaries and the shared-path environment
variable in its [browser installation guidance](https://playwright.dev/docs/browsers).

## Scope and Non-Goals

Change `gh-actions-runner/Dockerfile`, add `gh-actions-runner/install-chromium.sh` and
`gh-actions-runner/tests/check_browser_capabilities.cjs`, and update `gh-actions-runner/README.md`.
Keep this ExecPlan current and link it from the runner documentation.
The image build itself runs the new smoke check, so the existing pull request build gates its behavior.

Leave the launcher, worker entry point, stack resource settings, credentials, registry permissions, image tag,
deployment triggers, browser configurations, and LeadEmailFinder workflow commands unchanged. This pull request
adds Node, npm, `npx`, and global Playwright to the existing image. It does not add Firefox or WebKit, a shared
browser cache volume, a new runner pool, or a job container. Removing the residual operating system package
check is outside this plan.

The plan authorizes no infrastructure deployment. It changes no application HTTP behavior or database schema.

## Plan of Work

Add a `node:24-bookworm-slim` build stage to `gh-actions-runner/Dockerfile`. Copy its Node binary and npm
directory into `/usr/local` in the existing Ubuntu 22.04 image, and create the npm and `npx` command links.
Check that the copied tools run in the runner image. Workflows can still use `actions/setup-node` to select
another Node version.

Declare `PLAYWRIGHT_VERSION=1.63.0` and retain `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` for installation
and all later worker processes. Copy `gh-actions-runner/install-chromium.sh` into the image and invoke it with
`RUN sh /tmp/install-chromium.sh`. Keep `#!/bin/sh` and `set -eu`. The script runs
`npm install --global --no-audit --no-fund "playwright@$PLAYWRIGHT_VERSION"`, followed by
`playwright install --with-deps chromium`. npm handles package retrieval and integrity verification.

Install the complete assets selected by `chromium`, including its headless shell and FFmpeg. Do not use
`--only-shell` or change browser channels. This preserves both existing headed capabilities and the current
headless test behavior. Preserve the Ubuntu package repositories; the pinned Playwright installer selects its
system-library requirements. This plan pins the installer and browser revisions but does not claim that the
existing unpinned Ubuntu image and package repositories become reproducible byte for byte.

Make `/opt/ms-playwright` readable, executable, and writable by `runner`, and clear npm and package-manager
caches. Retain the global Playwright package and CLI. Remove the custom archive verification, integrity argument,
and diagnostic manifest; installed package metadata and `playwright --version` identify the installed version.

Update `gh-actions-runner/tests/check_browser_capabilities.cjs` to load the installed global Playwright package
and compare its version with the expected build argument. Its arguments are the absolute package directory
`/usr/local/lib/node_modules/playwright` and the expected version `1.63.0`. It verifies that the browser path is writable
by the current non-root user and launches both the default headless browser and
the `chromium` channel. Each launch loads a local HTML document, checks its title, captures an in-memory
screenshot, and closes the browser in a `finally` block. It writes no test artifact containing application data.

After browser installation, use separate short `RUN --network=none` instructions to run
`playwright install chromium` and then the browser checker. Both instructions use `runuser` to execute as `runner`.
Remove the copied build scripts in a separate cleanup instruction after those checks.
The checks must fail the image build for missing libraries, missing binaries, the wrong package version, or
inaccessible browser files. Use the existing image build workflow to run it
for pull requests and before publication. Do not add credential access or change bootstrap runner labels.

Document how to update `PLAYWRIGHT_VERSION` when the consumer lockfile changes. Existing jobs
with another Playwright version retain their writable, disposable browser directory and standard installer.
After publication and an authorized deployment, compare the existing browser setup step with its prior run;
record downloads, installed packages, and elapsed time separately from full workflow completion.

## Interfaces and Dependencies

The image provides Node 24, npm, `npx`, and Playwright `1.63.0` on `PATH`, plus
`PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`. Consumer package scripts continue to resolve the version selected
by their frozen lockfile. The build does not set a global `NODE_PATH` or override consumer dependencies.

The POSIX provisioning script depends on npm and the installed Playwright CLI. Playwright selects the browser
downloads and corresponding Ubuntu libraries. The global package remains installed. The existing
`RUNNER_TOOL_CACHE`, credential boundaries, workspace mounts, private daemon, and cleanup mechanism remain unchanged.

## Acceptance Criteria

- A clean image build installs exactly Playwright `1.63.0` globally through npm and installs its Chromium,
  headless shell, FFmpeg, and required operating system libraries.
- As `runner`, Node, npm, `npx`, and Playwright resolve on `PATH` and report their installed versions.
- As the ordinary `runner` user, the exact Playwright package launches both tested Chromium modes and captures
  a screenshot without network access. Missing binaries or libraries make the image build fail.
- In a fresh final-image container with a new volume over `/actions-runner/_work`, the same package's
  `install chromium` command succeeds without network access and its browser launch check passes. The image
  package cache remains visible under `/opt/ms-playwright`.
- Repeating the existing full `install --with-deps chromium` command with network access does not download the
  matching browser assets again. Any remaining package index or dependency check is recorded honestly.
- The worker can create and remove a synthetic file in the browser directory. A second fresh worker does not
  inherit that file or a synthetic file created in the first worker's home.
- The final image retains global Playwright and its package metadata. Build scripts and custom diagnostic
  metadata are absent; npm and package-manager caches are cleared after installation.
- All existing mocked lifecycle and deployment tests pass. The worker continues to receive only its private
  daemon socket, fresh workspace, and short-lived registration token.
- The existing pull request image build passes before publication. Live setup-time improvement remains pending
  until a deployed image is observed in LeadEmailFinder; source validation does not claim that result.

## Validation

From the Swarm repository root, run the existing focused checks and build the image:

```sh
dash -n gh-actions-runner/install-chromium.sh
node --check gh-actions-runner/tests/check_browser_capabilities.cjs
python3 -m unittest discover -s gh-actions-runner/tests -v
bash -n gh-actions-runner/entrypoint.sh gh-actions-runner/runner-entrypoint.sh
docker stack config -c gh-actions-runner/gh-actions-runner.yml
BUILDX_CONFIG=/tmp/runner-browser-buildx docker build --file gh-actions-runner/Dockerfile --tag gh-actions-runner:chromium-check-20260914 .
git diff --check
```

When ShellCheck is available, also run `shellcheck --shell=sh gh-actions-runner/install-chromium.sh`.

The image build runs `check_browser_capabilities.cjs` offline as `runner`. Check the retained commands and global
package version in a fresh container, then run the same browser checker against the installed package. From the
Swarm repository root, mount only the checker as a read-only file and run:

```sh
docker run --rm --network none --shm-size 1g \
  --mount type=volume,destination=/actions-runner/_work \
  --mount "type=bind,source=$PWD/gh-actions-runner/tests/check_browser_capabilities.cjs,target=/tmp/check_browser_capabilities.cjs,readonly" \
  --user runner --entrypoint /bin/sh gh-actions-runner:chromium-check-20260914 -ec '
    node --version
    npm --version
    npx --version
    playwright --version
    npm list --global --depth=0
    playwright install chromium
    node /tmp/check_browser_capabilities.cjs /usr/local/lib/node_modules/playwright 1.63.0
    test ! -e /opt/ms-playwright/previous-worker
    test ! -e /home/runner/previous-worker
    touch /opt/ms-playwright/previous-worker /home/runner/previous-worker
  '
```

Run this command twice. Both runs must pass; each starts a new image filesystem and disposable workspace volume.
Repeat the exact existing installation command inside a disposable container with normal network access,
using `playwright install --with-deps chromium` as `runner`. Compare its logs to the offline reuse check:
package management may still access its indexes, but browser asset downloads must be absent. Remove the local
image when evidence has been captured. Do not start the runner entry point or register with GitHub.

Use disposable checks to confirm that an unavailable npm package version fails installation and that the browser
checker rejects an unexpected package version, inaccessible browser files, and missing browser executables.
Record the resolved Node and npm versions from the built image. Verify that workflow-selected Node versions can
still take precedence on `PATH` without changing the installed global browser assets.

Run shell and workflow linters if their files change while implementing; unexpected changes to those files must
still fit this image-provisioning outcome. Run Harper from the LeadEmailFinder root using the actual final plan
path and runner README:

```sh
corepack pnpm docs:lint -- /home/kyrylo/WebstormProjects/worktrees/swarm-browser-ci-plans/gh-actions-runner/README.md /home/kyrylo/WebstormProjects/worktrees/swarm-browser-ci-plans/docs/plans/browser-ci/01-preinstall-chromium.md
```

After operational authorization, use the existing build and deployment procedures in the runner README. Capture
the image digest before and after the update, verify service convergence and online worker labels, then run the
unchanged LeadEmailFinder validation workflow. The submitted deployment, registered workers, skipped downloads,
job timings, and entire workflow result are separate evidence. No such operational check ran during planning.

Bruno: not applicable — runner image provisioning does not change application HTTP behavior.

## Idempotence and Recovery

Image builds create disposable layers and may be retried after failed downloads. A failed npm installation or
browser smoke check prevents a candidate image from passing the build. Consumer installation is safe to repeat:
matching binaries remain available and additional writes stay in that worker's disposable layer.

Keep local validation resources uniquely named or anonymous and remove only those resources. The validation
commands use no host socket, registration credential, or host-wide prune operation. Preserve unrelated checkout
changes and other CI job resources.

For an operational rollback, record the previous deployed isolated image digest before updating the mutable
tag. Restore that prior isolated image through the existing deployment procedure and verify convergence.
Consumer installation commands still provision any missing browser assets. Preserve `docker-isolated`; do not
restore an older image that exposes the Swarm host daemon. The retained nightly deployment schedule means a
temporary service rollback alone is insufficient if tracked source still selects the candidate image.

## Artifacts and Notes

Historical local implementation validation on 2026-09-14 at commit `f8d4282`, before the readability refactor:

- `python3 -m unittest discover -s gh-actions-runner/tests -v`: all 20 tests passed.
- The documented shell syntax, stack rendering, and whitespace checks passed. Node syntax validation passed.
- The documented Docker build passed, including offline installation reuse and both browser launch checks.
- Two fresh final-image checks passed in 3.02 and 2.18 seconds, including container startup, the offline installer,
  both launch modes, and isolation markers. No registration entry point or credentials were used.
- The same CLI with `install --with-deps chromium` passed in a fresh container as `runner` in 9.10 seconds.
  It downloaded package indexes but no browser assets; zero packages were newly installed.
- Disposable negative checks rejected a wrong browser path, mismatched version metadata, inaccessible browsers,
  and missing browser executables. Each reported the correct error message.
- The documented Harper command passed for both Markdown files from `/home/kyrylo/WebstormProjects/LeadEmailFinder`.

Historical JavaScript readability refactor validation on 2026-09-14 at commit `a5b8a9c`:

- Node syntax validation passed for `install-chromium.cjs`, and all 20 existing tests passed again.
- The image build passed with the tag `gh-actions-runner:chromium-readable-20260914`, including both offline gates.
- A build with `--build-arg PLAYWRIGHT_INTEGRITY=sha512-invalid` failed at archive verification before extraction
  or installer execution.
- Two fresh containers passed offline reuse, both launch modes, cleanup, and isolation checks in 1.96 and
  1.85 seconds. The copied provisioning script was also absent from the final image.
- The existing installer flags passed in 10.43 seconds locally, with zero browser downloads and no new packages.
- Independent review found no actionable issues. The documented Harper command passed for both Markdown files.

Historical POSIX archive installer validation on 2026-09-14 at commit `df33322`:

- `dash -n gh-actions-runner/install-chromium.sh` passed.
- `docker run --rm -i --network none koalaman/shellcheck:v0.11.0 --shell=sh - < gh-actions-runner/install-chromium.sh`
  passed, and all 20 existing lifecycle and deployment tests passed again.
- The image build passed with the tag `gh-actions-runner:chromium-posix-20260914`, including both offline gates.
- An invalid archive checksum failed the build before extraction. Disposable tests also rejected missing integrity
  and a verified synthetic archive with a mismatched package version before metadata creation or installer execution.
- Two fresh containers passed offline reuse, both launch modes, cleanup, and isolation checks in 1.90 and
  1.85 seconds. The temporary checksum file, installer package, and copied scripts were absent from the final image.
- The existing installer flags passed in 8.78 seconds locally, with zero browser downloads and no new packages.
- Independent review found no actionable issues. The documented Harper command passed for both Markdown files.

Global npm installation validation on 2026-09-14:

- The full image build passed, including offline browser reuse and both launch checks as `runner`.
  The resolved tools are Node `24.21.0`, npm and `npx` `11.19.0`, and Playwright `1.63.0`.
  The Node image resolved to `sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553`.
- `dash -n`, Node syntax validation, ShellCheck `--shell=sh`, and whitespace checks passed.
  All 20 existing lifecycle and deployment tests passed.
- Two fresh workers with disposable workspace volumes passed in 3.35 and 3.23 seconds. Both reused and launched
  Chromium offline through the global package and a separate copy representing the consumer package. Both launch
  modes, browser writes, build-script cleanup, and isolation markers passed.
- An unavailable npm version stopped the installer before browser installation. The checker rejected a wrong
  expected version, a wrong browser path, inaccessible browser files, and missing executables.
- Prepending the runner's bundled Node 20 directory selected Node `20.20.2`; the retained Playwright CLI still
  reported `1.63.0` and reused Chromium offline. This checks ordinary `PATH` precedence locally, not a live
  `actions/setup-node` run.
- The existing `install --with-deps chromium` flags passed in 10.09 seconds locally, with zero browser downloads
  and zero newly installed packages. This measures the remaining local package checks, not a CI speedup.
- Independent review found no actionable issues. The documented Harper command passed for both Markdown files.

The earlier checksum and manifest checks belong to the retired archive installer. This revision delegates
package retrieval and integrity verification to npm and checks the retained package version and browser runtime.

The [Playwright browser documentation](https://playwright.dev/docs/browsers) supports the shared browser path
and version-specific installation behavior. Local validation of the global npm installation passed.
Deployment and CI performance remain unverified.

Suggested pull request title: `perf(runners): preinstall Chromium for browser validation`.
The expected final location is `docs/plans/browser-ci/01-preinstall-chromium.md` in Swarm. This plan may proceed
independently of LeadEmailFinder's job budget, build reuse, and workflow split changes.

## Plan readiness

Ready to implement
