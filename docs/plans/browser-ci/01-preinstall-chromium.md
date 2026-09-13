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

- [ ] (2026-09-13) Bake Chromium and its system libraries into the existing worker image.
- [ ] (2026-09-13) Add checks for installation reuse, browser launch, permissions, and fresh worker state.
- [ ] (2026-09-13) Run local validation and document the image publication and operational verification procedure.

## Plan dependencies

None.

## Surprises & Discoveries

- (2026-09-13) The launcher mounts only the workspace and private socket into workers. `/home/runner` is fresh
  image filesystem state, not a mounted home volume. An image path outside the workspace survives its mount.
- (2026-09-13) Stack environment variables do not automatically reach workers. The launcher explicitly passes
  registration and runner settings, so the browser location must be defined with `ENV` in the Dockerfile.
- (2026-09-13) The image has runner-provided Node executables but does not install a global Node package manager.
  `playwright-core@1.63.0` has no runtime package dependencies and supports Node 20 or later. Its checked archive
  can run directly with the runner's bundled Node 24 executable.
- (2026-09-13) Swarm PR #75 added `gh-actions-runner/tests/check_git_capabilities.py` and runs it during the
  image build. Preserve that existing Git capability check when adding the browser check.

## Decision Log

- Decision: Extend the existing Ubuntu 22.04 isolated runner image.
  Rationale: The private daemon, matching workspace mounts, localhost ports, and ephemeral worker lifecycle are
  existing contracts. Browser provisioning does not require changing those contracts or replacing the base image.
  Date/Author: 2026-09-13, Codex planning.
- Decision: Install with exactly `playwright-core@1.63.0`, whose archive integrity matches LeadEmailFinder's
  `pnpm-lock.yaml`, using the runner's bundled Node executable.
  Rationale: This selects the repository's browser revisions without a global package-manager installation,
  an unversioned CLI download, or a change to the consuming application's dependencies.
  Date/Author: 2026-09-13, Codex planning.
- Decision: Use image-level `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` and make that directory writable by `runner`.
  Rationale: The path is outside the shared workspace. Each job writes only its own disposable container layer,
  including package links and any different browser version requested by another repository.
  Date/Author: 2026-09-13, Codex planning.
- Decision: Preserve LeadEmailFinder's existing `playwright install --with-deps chromium` command.
  Rationale: Matching versions reuse the installed binaries, while different locked versions retain the existing
  installation behavior. Deployment needs no coordinated consumer change or new scheduling label.
  Date/Author: 2026-09-13, Codex planning.

## Outcomes & Retrospective

Not started.

## Context and Orientation

At Swarm commit `47c193f1b43cd1e6283b23dde5924a1495c7da56`, `gh-actions-runner/Dockerfile` builds Ubuntu 22.04
with Actions runner `2.337.0`, Docker tooling, and general compilation libraries. It installs no Chromium.
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

LeadEmailFinder's `pnpm-lock.yaml` at commit `099d1d0872be67987b2f544468c21f89a858e4a3` resolves Playwright to
`1.63.0`. Its browser job executes `playwright install --with-deps chromium` after dependency installation.
The package's browser manifest selects Chromium and Chromium Headless Shell revision `1243`, browser version
`153.0.8010.12`, plus FFmpeg revision `1011`. Use the package manifest through its CLI rather than hardcoding
binary directory names. Playwright documents version-specific browser binaries and the shared-path environment
variable in its [browser installation guidance](https://playwright.dev/docs/browsers).

## Scope and Non-Goals

Change `gh-actions-runner/Dockerfile`, add `gh-actions-runner/tests/check_browser_capabilities.cjs`, and update
`gh-actions-runner/README.md`. Keep this ExecPlan current and link it from the runner documentation.
The image build itself runs the new smoke check, so the existing pull request build gates its behavior.

Leave the launcher, worker entry point, stack resource settings, credentials, registry permissions, image tag,
deployment triggers, browser configurations, and LeadEmailFinder workflow commands unchanged. This pull request
does not add Firefox or WebKit, a shared browser cache volume, a new runner pool, a global Playwright dependency,
or a job container. Removing the residual operating system package check is outside this plan.

The plan authorizes no infrastructure deployment. It changes no application HTTP behavior or database schema.

## Plan of Work

Add the browser provisioning layer after the existing Actions runner archive has been verified and extracted in
`gh-actions-runner/Dockerfile`. Declare build arguments for installer version `1.63.0` and the exact SHA-512
integrity shown under Artifacts and Notes. Download that exact `playwright-core` package archive from the npm
registry, verify its bytes before extraction, and fail the image build on a version or integrity mismatch.
Keep the installer in a temporary directory. Run its CLI with
`/actions-runner/externals/node24/bin/node` and `install --with-deps chromium` as root, setting
`PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` for installation and all later worker processes.

Install the complete assets selected by `chromium`, including its headless shell and FFmpeg. Do not use
`--only-shell` or change browser channels. This preserves both existing headed capabilities and the current
headless test behavior. Preserve the Ubuntu package repositories; the pinned Playwright installer selects its
system-library requirements. This plan pins the installer and browser revisions but does not claim that the
existing unpinned Ubuntu image and package repositories become reproducible byte for byte.

Make `/opt/ms-playwright` readable, executable, and writable by `runner`. Keep the installer package readable
while the image checks run, then remove it, its archive, and temporary build files. Retain a small JSON manifest
at `/opt/runner-playwright.json` containing the exact installer version, archive integrity, browser path, and
browser revision manifest. This is diagnostic metadata; consumers continue to use their own installed package.

Add `gh-actions-runner/tests/check_browser_capabilities.cjs`. Give it the absolute path of the unpacked
`playwright-core` package as its only argument. It verifies package version against the image metadata, verifies
the browser path is writable by the current non-root user, and launches both the default headless browser and
the `chromium` channel. Each launch loads a local HTML document, checks its title, captures an in-memory
screenshot, and closes the browser in a `finally` block. It writes no test artifact containing application data.

Run that checker as `runner` in a Dockerfile `RUN --network=none` instruction after browser installation and
before removing the temporary package. The check must fail the image build for missing libraries, missing
binaries, wrong version metadata, or inaccessible browser files. Use the existing image build workflow to run it
for pull requests and before publication. Do not add credential access or change bootstrap runner labels.

Document how to update both installer version and integrity when the consumer lockfile changes. Existing jobs
with another Playwright version retain their writable, disposable browser directory and standard installer.
After publication and an authorized deployment, compare the existing browser setup step with its prior run;
record downloads, installed packages, and elapsed time separately from full workflow completion.

## Interfaces and Dependencies

The new image contract is `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`, inherited by workers from their image.
The diagnostic manifest is `/opt/runner-playwright.json`. Browser code continues to resolve the version selected
by the consumer's frozen lockfile, without a global `NODE_PATH`, CLI shim, or Playwright dependency override.

The image build uses the runner's bundled Node 24 executable, the exact npm package archive, and Playwright's
version-selected browser downloads. It installs the corresponding Ubuntu libraries during the image build.
The installer package is temporary. The existing `RUNNER_TOOL_CACHE`, credential boundaries, workspace mounts,
private daemon, and cleanup mechanism remain unchanged.

## Acceptance Criteria

- A clean image build verifies the exact installer archive before running it and installs Chromium, its headless
  shell, FFmpeg, and the required operating system libraries for Playwright `1.63.0`.
- As the ordinary `runner` user, the exact Playwright package launches both tested Chromium modes and captures
  a screenshot without network access. Missing binaries or libraries make the image build fail.
- In a fresh final-image container with a new volume over `/actions-runner/_work`, the same package's
  `install chromium` command succeeds without network access and its browser launch check passes. The image
  package cache remains visible under `/opt/ms-playwright`.
- Repeating the existing full `install --with-deps chromium` command with network access does not download the
  matching browser assets again. Any remaining package index or dependency check is recorded honestly.
- The worker can create and remove a synthetic file in the browser directory. A second fresh worker does not
  inherit that file or a synthetic file created in the first worker's home.
- The temporary installer package and archive are absent from the final image. The diagnostic manifest records
  the version and integrity actually used to build it.
- All existing mocked lifecycle and deployment tests pass. The worker continues to receive only its private
  daemon socket, fresh workspace, and short-lived registration token.
- The existing pull request image build passes before publication. Live setup-time improvement remains pending
  until a deployed image is observed in LeadEmailFinder; source validation does not claim that result.

## Validation

From the Swarm repository root, run the existing focused checks and build the image:

```sh
python3 -m unittest discover -s gh-actions-runner/tests -v
bash -n gh-actions-runner/entrypoint.sh gh-actions-runner/runner-entrypoint.sh
docker stack config -c gh-actions-runner/gh-actions-runner.yml
BUILDX_CONFIG=/tmp/runner-browser-buildx docker build --file gh-actions-runner/Dockerfile --tag gh-actions-runner:browser-check .
git diff --check
```

The image build runs `check_browser_capabilities.cjs` offline as `runner`. Inspect the final image metadata and
stage a fresh copy of the exact verified installer package for the final-image check. Use a temporary directory
outside the repository, verify the archive with Node's `crypto` SHA-512 digest against the recorded integrity,
and extract only after verification. Do not install it in the host dependency tree. Place the checker in that
directory next to the unpacked `playwright-core` directory, and grant the container's `runner` user read and
traverse access to this synthetic fixture. Set `runner_browser_fixture` to this prepared
directory and run:

```sh
docker run --rm --network none --shm-size 1g \
  --mount type=volume,destination=/actions-runner/_work \
  --mount "type=bind,source=$runner_browser_fixture,target=/browser-check,readonly" \
  --user runner --entrypoint /bin/bash gh-actions-runner:browser-check -ec '
    /actions-runner/externals/node24/bin/node /browser-check/playwright-core/cli.js install chromium
    /actions-runner/externals/node24/bin/node /browser-check/check_browser_capabilities.cjs /browser-check/playwright-core
    test ! -e /opt/ms-playwright/previous-worker
    test ! -e /home/runner/previous-worker
    touch /opt/ms-playwright/previous-worker /home/runner/previous-worker
  '
```

Run this command twice. Both runs must pass; each starts a new image filesystem and disposable workspace volume.
Repeat the exact existing installation command inside a disposable container with normal network access,
using the staged CLI and `install --with-deps chromium` as `runner`. Compare its logs to the offline reuse check:
package management may still access its indexes, but browser asset downloads must be absent. Remove the temporary
fixture and local image when evidence has been captured. Do not start the runner entry point or register with GitHub.

Run shell and workflow linters if their files change while implementing; unexpected changes to those files must
still fit this image-provisioning outcome. Run Harper from the LeadEmailFinder root using the actual final plan
path and runner README:

```sh
corepack pnpm docs:lint -- /home/kyrylo/WebstormProjects/Swarm/gh-actions-runner/README.md /home/kyrylo/WebstormProjects/Swarm/docs/plans/browser-ci/01-preinstall-chromium.md
```

After operational authorization, use the existing build and deployment procedures in the runner README. Capture
the image digest before and after the update, verify service convergence and online worker labels, then run the
unchanged LeadEmailFinder validation workflow. The submitted deployment, registered workers, skipped downloads,
job timings, and entire workflow result are separate evidence. No such operational check ran during planning.

Bruno: not applicable — runner image provisioning does not change application HTTP behavior.

## Idempotence and Recovery

Image builds create disposable layers and may be retried after failed downloads. A failed integrity check or
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

The current installer archive is
`https://registry.npmjs.org/playwright-core/-/playwright-core-1.63.0.tgz`, with integrity:

```text
sha512-rYCsBF/M5HjUch52bbtVONEFjv6Xu8sm8h72dNlR5bzIE1fvC/bxgspzkjSfU+MweEMmPM8KJebG6nnyxo5mCg==
```

The package registry metadata and archive contents were inspected on 2026-09-13; the integrity matches the
consumer lockfile. The package CLI is self-contained, and its manifest selects the browser revisions stated above.
The [Playwright browser documentation](https://playwright.dev/docs/browsers) supports the shared browser path
and version-specific installation behavior. Compatibility with the final runner image must still be established
by the prescribed build and runtime checks.

Suggested pull request title: `perf(runners): preinstall Chromium for browser validation`.
The expected final location is `docs/plans/browser-ci/01-preinstall-chromium.md` in Swarm. This plan may proceed
independently of LeadEmailFinder's job budget, build reuse, and workflow split changes.

## Plan readiness

Ready to implement
