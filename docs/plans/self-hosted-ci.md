# Run CI Jobs with Private Docker Daemons

This is a living implementation plan for exactly one Swarm pull request. Keep progress, discoveries, decisions,
and validation evidence current while implementing the runner infrastructure change.

## Purpose / Big Picture

Provide GitHub Actions jobs with a fresh worker and private Docker daemon so application CI can build images,
bind service ports, and remove disposable Compose stacks without sharing Docker resources with other jobs.
The new pool advertises `self-hosted`, `swarm`, `ubuntu-22`, and `docker-isolated`.

## Progress

- [x] (2026-09-12) Inspect the existing runner image, launcher, stack, and build and deployment workflows.
- [x] (2026-09-12) Fix the design and separate this infrastructure pull request from LeadEmailFinder workflow targets.
- [x] (2026-09-12) Implement launcher and worker lifecycles with one private daemon and fresh volumes per job.
- [x] (2026-09-12) Update image and resource configuration while preserving deployment triggers.
- [x] (2026-09-12) Pass 13 mocked lifecycle tests, shell syntax checks, and Harper validation of this plan.
- [x] (2026-09-12) Build the updated runner image with the required environment and tools.
- [x] (2026-09-12) Rebuild the final entry point layer and verify runner, Node, Compose, and workspace mounts.
- [x] (2026-09-12) Verify private daemons, localhost services, workspace mounts, and Ruby setup with the final image.
- [x] (2026-09-12) Prepare the source for review against current `master`, preserving its updated secret reference.
- [ ] (2026-09-12) After separate operational authorization, deploy the pool and record live isolation and CI evidence.

## Plan dependencies

None.

## Surprises & Discoveries

- (2026-09-12) The existing worker mounts `/var/run/docker.sock` from the Swarm host and receives the organization
  personal access token. Application cleanup commands therefore reach shared Docker resources.
- (2026-09-12) The existing stack runs six small workers, while the expanded LeadEmailFinder jobs require Docker
  builds, language tooling, browser dependencies, and a complete disposable application stack.
- (2026-09-12) A bootstrap image build must remain compatible with the existing runner version until the upgraded
  image has been published and deployed.
- (2026-09-12) Publication checks found newer `master` commits that selected runner `2.333.1` and secret
  `gh_pat_20260912`. This change advances the runner to `2.337.0` and preserves that secret reference.

## Decision Log

- Decision: Keep the Swarm host socket and GitHub personal access token only in a trusted launcher.
  Rationale: The launcher provisions and cleans up job resources; application jobs receive only a private daemon
  socket and the short-lived token needed to register their ephemeral worker.
  Date/Author: 2026-09-12, user-authorized implementation.
- Decision: Give each job one worker and one privileged Docker-in-Docker daemon sharing a network namespace.
  Rationale: Existing localhost service ports and Docker bind mounts keep their expected behavior while Docker
  images, networks, containers, and volumes remain private to the job.
  Date/Author: 2026-09-12, implementation.
- Decision: Start with one launcher replica, reserving four CPUs with `memory: 8G` for its worker pair.
  Rationale: Bound concurrency while validating the pool. Each worker and daemon has two CPUs and a `--memory 4g` limit.
  Date/Author: 2026-09-12, implementation.
- Decision: Bootstrap through manual dispatch, retain nightly runner deployment, and require `docker-isolated`.
  Rationale: Preserve existing triggers while keeping initial operational rollout separate from local source work.
  The old shared-daemon workers must not accept the new application workflow jobs.
  Date/Author: 2026-09-12, user-authorized implementation.

## Outcomes & Retrospective

The launcher, worker, image, and stack changes are implemented locally. All 13 mocked lifecycle tests, shell syntax,
ShellCheck, and workflow `actionlint` checks passed. The final image built successfully. Local runtime checks verified
runner `2.337.0`, Node 24, Docker Compose, private Docker daemons, localhost services, and workspace mounts. The real
Ruby setup action installed `3.3.12` and passed a test using its standard test library. All local smoke resources were
removed. Harper passed this plan. No infrastructure deployment, GitHub runner registration, or live GitHub Actions
execution occurred during these checks.

## Context and Orientation

`gh-actions-runner/Dockerfile` builds the Ubuntu 22.04 runner image. `gh-actions-runner/entrypoint.sh` becomes the
launcher; `gh-actions-runner/runner-entrypoint.sh` owns worker setup and execution. The stack in
`gh-actions-runner/gh-actions-runner.yml` provisions the launcher with the host socket and existing secret.
`gh-actions-runner/tests/test_runner_lifecycle.py` verifies lifecycle behavior through controlled process fixtures.

`.github/workflows/build-push.yml` publishes the new isolated image with bootstrap actions compatible with Node 20.
`.github/workflows/deploy-gh-actions-runner.yml` retains manual dispatch and nightly rollout. LeadEmailFinder consumes the new
labels through a separate pull request and its `.agents/plans/self-hosted-runners/01-use-isolated-runners.md` plan.

## Scope and Non-Goals

This pull request changes the runner image, both scripts, runner stack, focused tests, related build
and deployment workflows, and documentation. Its observable outcome is one disposable worker and daemon per job.

It does not change LeadEmailFinder application code or workflow targets, deploy the Swarm stack, rotate the existing
organization secret, modify unrelated services, or prune host Docker resources. No application migration is needed.
Privileged daemon containers remain trusted host workloads; this design provides Docker state isolation for CI.

## Plan of Work

Update the Ubuntu 22.04 image to Actions runner `2.337.0` and install the concrete prerequisites needed by current
jobs: Docker CLI and Compose, Git, `curl`, `jq`, archive tools, and compilation tooling. Include Ruby runtime
libraries and passwordless `sudo` so workflows can install browser system dependencies. Preserve compatibility
with Node setup and Corepack so workflows can select Node 24.

Refactor the existing entry point into a launcher that obtains a short-lived registration token, assigns unique
owned resource names, and creates fresh workspace, socket, and Docker data volumes. The worker home is fresh
container filesystem state. Start a private privileged
daemon, wait for readiness, then start one ephemeral worker. Mount shared workspace and socket paths consistently
in both containers and share the daemon's network namespace so host-side tests reach published service ports.

Keep the host Docker socket and personal access token out of the worker. Register it with the new capability label
and ephemeral mode, execute one job, then stop and remove exactly that worker pair and its owned volumes. Preserve
exit status and clean up partial startup, job failure, and graceful interruption. Do not use host-wide pruning.

Set worker and daemon limits to two CPUs with `--memory 4g` each. Reserve four CPUs with `memory: 8G` in the launcher
service and start at one replica. Publish the new image through a bootstrap workflow that can run on the existing
pool. Preserve manual dispatch and the nightly deployment schedule. Keep the application workflow switch inactive
until the upgraded pool is deployed.

## Interfaces and Dependencies

The organization personal access token remains a launcher-only Swarm secret. The worker receives a short-lived
registration token, organization URL, unique runner name, workspace path, and the four selected labels. Its Docker
endpoint is the private daemon's local socket. The socket and workspace volumes use consistent paths in both
containers; the worker's home and all daemon state are fresh for every job.

The launcher requires permission to create sibling containers and a privileged Docker-in-Docker daemon on the
Swarm node. Runtime worker and daemon limits are two CPUs with `--memory 4g` each; the scheduler accounts for their
combined resources through the launcher reservation of four CPUs and `memory: 8G`. Replicas initially equal one.
Workers use a private control-group namespace so the Actions runner accepts its container environment. The published
isolated image must exist before the first rollout. Manual dispatch provides bootstrap; the retained nightly schedule
continues to deploy runner configuration after the source change merges.

## Acceptance Criteria

- Each registered worker advertises the required labels, accepts one job, and has a fresh home and workspace.
- Worker mounts and environment contain neither the host Docker socket nor the organization personal access token.
- A job's Docker client reaches only its private daemon; service ports remain reachable through localhost, and
  bind mounts expose the same workspace content that workflow commands create.
- Success, worker failure, interrupted startup, and graceful signals remove exactly the owned worker pair and
  volumes while preserving unrelated Docker resources.
- Worker and daemon limits, launcher reservation, and initial replica count match the documented budgets.
- Image publishing can bootstrap from the previous pool, and runner deployment preserves manual and nightly triggers.
- Focused automated checks pass. After authorized rollout, live tests prove daemon separation, fresh state across
  consecutive jobs, and successful LeadEmailFinder validation. Runtime criteria remain pending until observed.

## Validation

Run these focused checks from the Swarm repository root:

```sh
bash -n gh-actions-runner/entrypoint.sh gh-actions-runner/runner-entrypoint.sh
python3 -m unittest discover -s gh-actions-runner/tests -v
docker compose -f gh-actions-runner/gh-actions-runner.yml config --quiet
BUILDX_CONFIG=/tmp/self-hosted-ci-buildx docker build --file gh-actions-runner/Dockerfile --tag lef-self-hosted-runner:local .
git diff --check
shellcheck gh-actions-runner/entrypoint.sh gh-actions-runner/runner-entrypoint.sh
actionlint .github/workflows/*.yml
```

`bash -n gh-actions-runner/entrypoint.sh gh-actions-runner/runner-entrypoint.sh` passed on 2026-09-12.
`python3 -m unittest discover -s gh-actions-runner/tests -v` passed 13 tests. These tests cover private Docker context,
credential isolation, daemon readiness and worker failures, registration failure, ownership checks before removal,
attach disconnection, graceful signal handling, ephemeral registration, and token removal before listener startup.
Harper passed this plan using LeadEmailFinder's prose tooling and dictionary. Prose and mocked lifecycle checks do
not prove real Docker behavior. The image build command above passed with output recorded in
`/tmp/self-hosted-ci-image-build.log`, then passed again after the final script changes with output in
`/tmp/self-hosted-ci-image-build-final.log`. The final image identifier is
`afef65a0657df05d765135e1eab125b328eeafa5e3649271c454626094e03131`.

The local smoke script `/tmp/lef-ci-smoke-runner.sh` passed with output recorded in
`/tmp/lef-ci-smoke-runner.log`. Two private daemons proved nested workspace and temporary-file bind mounts,
localhost service access, private socket access without TCP listeners on ports 2375 or 2376, and separation of a
sentinel image and container from both the sibling daemon and host. The image also passed checks for the runner,
Node 24, `sudo`, Docker, Compose, and the real Ruby setup action installing `3.3.12`, including native libraries and
a standard-library test. These checks removed all their resources and performed no GitHub registration or deployment.

After separate operational authorization, publish the isolated image and invoke the manual deployment workflow.
Inspect registered runner labels and resource limits. Run consecutive disposable jobs that create a sentinel image,
volume, and workspace file, proving the next job starts without them. Verify a job cannot list the Swarm host's
containers, localhost service connectivity works, and cancellation removes only its owned resources. Finally run
the complete LeadEmailFinder validation workflow. No deployment or live test is authorized by this plan alone.

Bruno: not applicable — this change configures CI infrastructure without altering application HTTP behavior.

## Idempotence and Recovery

Use unique resource names and labels per worker pair. On ordinary completion or failure, resource removal must tolerate
partially created or already absent resources and preserve the original failure status. A fresh retry creates a new
pair and new state; no previous workspace or Docker state is reused.

A forced launcher kill or node loss can leave labeled sibling resources. Operational recovery must inspect their
ownership and remove only the identified inactive pair and volumes. Never run host-wide prune commands. If rollout
fails, stop accepting new work and restore the prior stack and image through the manual deployment procedure.
Keep new consumer workflows inactive while the previous pool is restored; removing `docker-isolated` would discard
their required isolation contract.

## Artifacts and Notes

The two-repository delivery order is Swarm source review and image publication, separately authorized infrastructure
deployment, then LeadEmailFinder workflow activation. Source checks, mocked lifecycle tests, container builds,
deployment state, and live CI results are distinct evidence. This plan records design, passing focused tests, and
successful local runtime checks. Deployment and live Actions scheduling remain unverified.

## Plan readiness

Implemented locally; deployment and live Actions verification remain pending.
