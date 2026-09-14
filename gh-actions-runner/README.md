# Isolated GitHub Actions Runners

The runner stack launches one fresh worker and one private Docker daemon for each GitHub Actions job.
Only the Swarm launcher receives the host Docker socket and the organization registration secret. The
worker receives a short-lived registration token, registers for one job, and uses its private Docker socket.

The worker and daemon share a network namespace and a workspace volume mounted at
`/actions-runner/_work` in both containers. Published service ports are therefore reachable at `localhost`,
and Docker bind mounts resolve the files checked out by the job. Image tags, containers, networks, volumes,
the worker home directory, and the workspace are isolated from other jobs. This allows LeadEmailFinder's
fixed development stack name and database ports to work without touching another job's stack.

The `docker-isolated` label is assigned only to these workers. Consumers select
`[self-hosted, swarm, ubuntu-22, docker-isolated]`; the launcher itself never registers as a runner.
The image contains Actions runner `2.337.0`, Ubuntu 22.04, Docker CLI and Compose, build tools, Python,
and passwordless `sudo` inside the worker for browser dependencies. Node and Ruby versions remain
selected by the consuming workflow. The Ruby tool cache at `/opt/hostedtoolcache` is writable.

Git comes from the stable Ubuntu Git Maintainers package archive recommended by the
[Git installation documentation](https://git-scm.com/install/linux). The image requires Git 2.50 or newer
because LeadEmailFinder's history scanner uses `git rev-list --objects --all -z` output delimited by null bytes.
The image build checks the version and tests reading a deleted file from Git history as the `runner` user.
The default Git 2.34 package in Ubuntu 22.04 silently produces incompatible output and causes that scanner to miss files.
The package archive supplies stable updates; rebuild with `--no-cache` to refresh the installed Git package.

## Chromium Runtime

The image includes Chromium, its headless shell, FFmpeg, and Linux libraries selected by Playwright `1.63.0`.
`PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` points every worker to these installed browsers. This directory
is writable by `runner` and lies outside the workspace mount. Each worker receives its own disposable copy
of any changes, so additional browser installations do not affect another job.

The build runs `install-chromium.cjs` with the Actions runner's bundled Node to verify the installer archive
against the integrity in LeadEmailFinder's lockfile and install the browser assets and libraries. Separate build
steps check browser reuse and launch both Chromium modes as `runner` without network access. The check renders
local HTML and captures screenshots in memory. The image retains `/opt/runner-playwright.json` with the installer
version, integrity, browser path, and revision manifest;
the temporary installer is removed after validation. Consuming workflows still install their own Playwright package.

Keep the existing `playwright install --with-deps chromium` command. Matching versions reuse installed browser
assets, while other versions can install their required browsers. The command still checks Linux packages and
may update package indexes. Preinstallation does not remove that work or establish a total browser-job duration.

When the consumer's frozen lockfile changes Playwright versions, update `PLAYWRIGHT_VERSION` and
`PLAYWRIGHT_INTEGRITY` together in the Dockerfile. Use the integrity for `playwright-core`, verify it against the
registry archive, and run the image build plus the fresh-container checks in the
[Chromium runtime plan](../docs/plans/browser-ci/01-preinstall-chromium.md). The CLI selects browser revisions;
do not update browser directory names by hand. After deployment, compare setup logs and elapsed time separately
from test execution and runner queue time.

## Capacity and Lifecycle

The stack has two launcher replicas, allowing up to two GitHub Actions jobs to run concurrently.
Each worker is limited to two CPUs and a memory limit of `4g`, and its Docker daemon has the same limits.
Each launcher reserves three CPUs and a memory reservation of `8G` in Swarm. The two slots therefore
reserve six CPUs and `16G` of memory. A node needs the available reservation before Swarm will schedule a slot.

The CPU reservation is a scheduling budget, below the combined four-CPU limit of each worker and daemon.
It allows two slots to fit on an eight-CPU node while leaving some CPU capacity unreserved for other services.
Both pairs can demand eight CPUs together, so jobs may take longer when their peaks overlap with other work.
This reservation is a starting point, not a measured minimum. Memory reservations still cover the combined
worker and daemon limits. Allow additional capacity for the launchers, host, and other services.
Increase replicas only after checking capacity, and review the reservations whenever the worker or daemon
limits change. The existing development VM definition is not a sizing recommendation.

The rolling update setting `parallelism: 1` replaces one launcher at a time during deployment. It does not
limit concurrent jobs; `replicas` controls the number of available slots.

After the job ends, the launcher removes its worker, daemon, and three named volumes. Failed startup
and ordinary termination use the same cleanup. A new Swarm task starts another fresh pair. The launcher
never prunes the host. Resource labels identify the owning launcher container:
`tuposoft.actions-runner.owner=<container-id>`.

A forced kill or node failure can prevent resource removal. Before removing an orphan, verify that its owning
launcher is gone and that its worker is no longer running a job. Remove only containers and volumes
with that exact owner label. Do not prune the host to recover one runner.

## Build and Rollout

Build and deploy the Swarm changes before enabling LeadEmailFinder's new runner labels.

1. Review the stack's capacity reservation and existing `gh_pat_20260912` secret. The secret needs
   permission to register and remove runners for `TupoSoft`. Preserve its existing value.
2. Run **Build and Push Images** on `master`. Its Node 20 actions can execute on the old runner pool.
   The workflow tests the lifecycle scripts and publishes `ghcr.io/tuposoft/gh-actions-runner:self-hosted-ci`.
   It leaves the previous `latest` tag intact. Pull requests from this repository build without publishing
   on the existing pool, so they can validate the image before the isolated pool is deployed. Builds from
   fork pull requests remain disabled.
3. Configure the registry pull credentials described below. The deployment workflow requires these settings
   and checks access to the runner image before submitting an update.
4. Run **Deploy GitHub Actions Runner**. Its bootstrap job also supports the old pool. It uses temporary
   SSH credentials and Docker configuration, then submits the stack update without waiting for it to
   converge. Replacing a runner service can stop a job, so deploy during a quiet period.
5. Check Swarm service convergence and confirm that both workers with all four labels are online in GitHub.
   A successful deployment job proves only that the update was submitted.
6. Enable LeadEmailFinder's workflow changes. Run full validation, including backend service containers,
   the browser stack reset and cleanup, and an ExecPlan synchronization dry run. Confirm that a second
   job can run concurrently with its own workspace and Docker daemon, and that cleanup for one job
   leaves the other job running.

The deployment workflow also retains its daily schedule. Image publishing is limited to `master`;
the deployment job also requires `master`. General stack deployment workflows use the isolated pool
and retain their existing remote Docker deployment behavior.

For rollback, restore the preceding runner stack configuration and its `latest` image, then restore
the preceding consumer labels if necessary. Existing jobs requiring `docker-isolated` will queue until
that pool is available. Never add the isolation label to a runner that shares the host Docker daemon.

## Registry Pull Credentials

Swarm can pull the private runner image after the deployment job ends or when it schedules a replacement
task. The job's `GITHUB_TOKEN` expires when the job finishes, so detached deployment requires a separate
credential that remains valid for those pulls. Image publishing still uses its own `GITHUB_TOKEN`.

Create a dedicated personal access token (classic) with `read:packages`. Its owner must have read access to
the `TupoSoft/gh-actions-runner` package. If the organization uses single sign-on, authorize the token for it.
Use this package credential separately from the runner registration secret. See
[GitHub's container registry authentication requirements](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
and [job token lifetime](https://docs.github.com/en/actions/concepts/security/github_token).

Set the following in the `TupoSoft/Swarm` repository. These commands prompt for the username and token;
enter the token through the secret prompt:

```bash
gh variable set GHCR_PULL_USERNAME --repo TupoSoft/Swarm
gh secret set GHCR_PULL_TOKEN --repo TupoSoft/Swarm
```

`GHCR_PULL_USERNAME` must be the token owner's GitHub username. The deployment checks both settings,
logs in through standard input, and verifies access to `:self-hosted-ci` before updating the stack.
Swarm receives the registry credentials through `--with-registry-auth`; the workflow removes its temporary
SSH and Docker configuration when it exits.

Rotate the token before expiration and rerun deployment to refresh the credentials stored by Swarm.
Confirm that the service runs two `:self-hosted-ci` replicas and that both isolated workers register in GitHub.
Workflow success alone does not establish service convergence.

## Local Validation

Run from the Swarm repository root:

```bash
python3 -m unittest discover -s gh-actions-runner/tests -v
bash -n gh-actions-runner/entrypoint.sh gh-actions-runner/runner-entrypoint.sh
docker stack config -c gh-actions-runner/gh-actions-runner.yml
docker build -f gh-actions-runner/Dockerfile -t gh-actions-runner:check .
actionlint .github/workflows/*.yml
```

The lifecycle tests use fake Docker and GitHub clients; they do not register runners or change Swarm.
The Docker build runs `gh-actions-runner/tests/check_git_capabilities.py` against the installed Git binary.
That check runs inside the new image so an older bootstrap runner can still build its replacement.
Container image checks and a local private-daemon smoke test provide separate evidence. Live GitHub
scheduling and full LeadEmailFinder validation require the deployed pool and are not proved by static
checks or mocked tests.
