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

## Capacity and Lifecycle

The initial stack has one launcher replica. Each worker is limited to two CPUs and a memory limit of `4g`, and
its Docker daemon has the same limits. Each launcher reserves four CPUs and a memory reservation of `8G` in Swarm to account
for these sibling containers. A node needs that available capacity before Swarm will schedule a slot.
Increase replicas only after checking capacity, and update the Swarm reservation whenever the worker
or daemon limits change. The existing development VM definition is not a sizing recommendation.

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
   It leaves the previous `latest` tag intact. Pull requests build without publishing and require the
   isolated pool, so the first infrastructure change also needs the local validation below.
3. Run **Deploy GitHub Actions Runner**. Its bootstrap job also supports the old pool. It uses temporary
   SSH credentials and Docker configuration, then submits the stack update without waiting for it to
   converge. Replacing a runner service can stop a job, so deploy during a quiet period.
4. Check Swarm service convergence and confirm that a worker with all four labels is online in GitHub.
   A successful deployment job proves only that the update was submitted.
5. Enable LeadEmailFinder's workflow changes. Run full validation, including backend service containers,
   the browser stack reset and cleanup, and an ExecPlan synchronization dry run. Confirm that a second
   job starts with a fresh workspace and Docker daemon.

The deployment workflow also retains its daily schedule. Image publishing is limited to `master`;
the deployment job also requires `master`. General stack deployment workflows use the isolated pool
and retain their existing remote Docker deployment behavior.

For rollback, restore the preceding runner stack configuration and its `latest` image, then restore
the preceding consumer labels if necessary. Existing jobs requiring `docker-isolated` will queue until
that pool is available. Never add the isolation label to a runner that shares the host Docker daemon.

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
Container image checks and a local private-daemon smoke test provide separate evidence. Live GitHub
scheduling and full LeadEmailFinder validation require the deployed pool and are not proved by static
checks or mocked tests.
