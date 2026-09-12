import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/deploy-gh-actions-runner.yml"
PULL_TOKEN = "synthetic-durable-pull-token"
JOB_TOKEN = "synthetic-short-lived-job-token"
PRIVATE_KEY = "synthetic-deployment-private-key"
PULL_USERNAME = "registry-token-owner"
IMAGE = "ghcr.io/tuposoft/gh-actions-runner:self-hosted-ci"


def deployment_step():
    """Extract this named step and its literal shell block without a YAML dependency."""
    lines = WORKFLOW.read_text().splitlines()
    start = next(index for index, line in enumerate(lines)
                 if line.strip() == "- name: Deploy runner stack")
    step_indent = len(lines[start]) - len(lines[start].lstrip())
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].strip()
                and len(lines[index]) - len(lines[index].lstrip()) <= step_indent),
               len(lines))
    step = lines[start:end]
    run_index = next(index for index, line in enumerate(step) if line.strip() == "run: |")
    run_indent = len(step[run_index]) - len(step[run_index].lstrip())
    script = []
    for line in step[run_index + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= run_indent:
            break
        script.append(line[run_indent + 2:] if line.strip() else "")
    return "\n".join(step), "\n".join(script) + "\n"


FAKE_COMMAND = r'''#!/usr/bin/env python3
import base64
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path(os.environ["DEPLOY_FAKE_ROOT"])
scenario = os.environ.get("DEPLOY_SCENARIO", "success")
record = {"name": name, "args": args}

if name == "docker":
    config = Path(os.environ["DOCKER_CONFIG"])
    record.update({
        "docker_config": str(config),
        "docker_host": os.environ.get("DOCKER_HOST"),
        "docker_context": os.environ.get("DOCKER_CONTEXT"),
        "registry_token_present": "REGISTRY_TOKEN" in os.environ,
        "private_key_present": "SWARM_PRIVATE_KEY" in os.environ,
        "temp_mode": stat.S_IMODE(config.parent.stat().st_mode),
    })
    if args[0] == "login":
        record["password"] = sys.stdin.read()
    else:
        auth = json.loads((config / "config.json").read_text())["auths"]["ghcr.io"]["auth"]
        record["stored_auth"] = base64.b64decode(auth).decode()
elif name == "ssh":
    assert args[0] == "-F", args
    config = Path(args[1])
    identity = config.parent / "id_ed25519"
    record.update({
        "config": config.read_text(),
        "key_mode": stat.S_IMODE(identity.stat().st_mode),
        "key_matches": identity.read_text() == os.environ["DEPLOY_EXPECTED_PRIVATE_KEY"] + "\n",
    })

with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(record) + "\n")

if name == "mktemp":
    sys.exit(subprocess.run([os.environ["DEPLOY_REAL_MKTEMP"], *args]).returncode)
elif name == "ssh":
    sys.exit(0)
elif name != "docker":
    raise AssertionError(name)
elif args[0] == "login":
    if scenario == "login_failure":
        sys.exit(17)
    username = args[args.index("--username") + 1]
    auth = base64.b64encode((username + ":" + record["password"]).encode()).decode()
    (config / "config.json").write_text(json.dumps({"auths": {"ghcr.io": {"auth": auth}}}))
elif args[:2] == ["manifest", "inspect"]:
    if scenario == "manifest_failure":
        sys.exit(23)
    print('{"schemaVersion": 2}')
elif args[:2] == ["stack", "deploy"]:
    subprocess.run(["ssh", "runner-manager.invalid", "docker", "system", "dial-stdio"], check=True)
    sys.exit(29 if scenario == "deployment_failure" else 0)
else:
    raise AssertionError(args)
'''


class RunnerDeploymentTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="runner-deployment-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.runner_temp = self.root / "runner-temp"
        self.runner_temp.mkdir()
        home = self.root / "home"
        (home / ".ssh").mkdir(parents=True)
        (home / ".docker").mkdir()
        self.original_ssh = home / ".ssh/config"
        self.original_docker = home / ".docker/config.json"
        self.original_ssh.write_text("existing SSH configuration\n")
        self.original_docker.write_text('{"existing": "Docker configuration"}\n')
        fake = self.bin / "fake"
        fake.write_text(FAKE_COMMAND)
        fake.chmod(0o755)
        for name in ("docker", "ssh", "mktemp"):
            (self.bin / name).symlink_to(fake)
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(home),
            "RUNNER_TEMP": str(self.runner_temp),
            "DEPLOY_FAKE_ROOT": str(self.root),
            "DEPLOY_REAL_MKTEMP": shutil.which("mktemp"),
            "DEPLOY_EXPECTED_PRIVATE_KEY": PRIVATE_KEY,
            "SWARM_HOST": "ssh://runner-manager.invalid",
            "SWARM_PRIVATE_KEY": PRIVATE_KEY,
            "REGISTRY_USERNAME": PULL_USERNAME,
            "REGISTRY_TOKEN": PULL_TOKEN,
            "GITHUB_ACTOR": "different-workflow-actor",
            "GITHUB_TOKEN": JOB_TOKEN,
            "DOCKER_CONTEXT": "inherited-context",
            "DOCKER_HOST": "ssh://unrelated-host.invalid",
        }

    def calls(self, name=None):
        log = self.root / "calls.jsonl"
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return [call for call in calls if name is None or call["name"] == name]

    def run_deployment(self, scenario="success", **env):
        _, script = deployment_step()
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=REPOSITORY_ROOT,
            env={**self.env, "DEPLOY_SCENARIO": scenario, **env},
            capture_output=True, text=True, timeout=10,
        )
        for secret in (PULL_TOKEN, JOB_TOKEN, PRIVATE_KEY):
            self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(list(self.runner_temp.iterdir()), [], "temporary credentials survived")
        self.assertEqual(self.original_ssh.read_text(), "existing SSH configuration\n")
        self.assertEqual(self.original_docker.read_text(), '{"existing": "Docker configuration"}\n')
        return result

    def test_workflow_binds_dedicated_pull_credentials(self):
        step, script = deployment_step()
        self.assertIn("REGISTRY_USERNAME: ${{ vars.GHCR_PULL_USERNAME }}", step)
        self.assertIn("REGISTRY_TOKEN: ${{ secrets.GHCR_PULL_TOKEN }}", step)
        self.assertNotIn("secrets.GITHUB_TOKEN", step)
        self.assertNotIn("github.token", step)
        self.assertNotIn("GITHUB_ACTOR", script)

    def test_missing_username_fails_before_temporary_files_or_authentication(self):
        result = self.run_deployment(REGISTRY_USERNAME="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GHCR_PULL_USERNAME", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_token_cannot_fall_back_to_the_job_token(self):
        result = self.run_deployment(REGISTRY_TOKEN="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GHCR_PULL_TOKEN", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_deployment_uses_durable_credentials_and_removes_local_auth(self):
        result = self.run_deployment()
        self.assertEqual(result.returncode, 0, result.stderr)
        login, manifest, deploy = self.calls("docker")
        self.assertEqual(login["args"],
                         ["login", "ghcr.io", "--username", PULL_USERNAME, "--password-stdin"])
        self.assertEqual(login["password"], PULL_TOKEN)
        self.assertEqual(manifest["args"], ["manifest", "inspect", IMAGE])
        self.assertEqual(deploy["args"],
                         ["stack", "deploy", "--with-registry-auth", "--prune", "--detach=true",
                          "-c", "gh-actions-runner/gh-actions-runner.yml", "gh-actions-runner"])
        for call in (manifest, deploy):
            self.assertEqual(call["stored_auth"], f"{PULL_USERNAME}:{PULL_TOKEN}")
            self.assertFalse(call["registry_token_present"])
        for call in (login, manifest, deploy):
            self.assertEqual(call["docker_host"], "ssh://runner-manager.invalid")
            self.assertIsNone(call["docker_context"])
            self.assertFalse(call["private_key_present"])
            self.assertEqual(call["temp_mode"], 0o700)
            self.assertTrue(Path(call["docker_config"]).is_relative_to(self.runner_temp))
            self.assertNotIn(PULL_TOKEN, " ".join(call["args"]))
        ssh, = self.calls("ssh")
        self.assertEqual(ssh["key_mode"], 0o600)
        self.assertTrue(ssh["key_matches"])
        self.assertIn("IdentitiesOnly yes", ssh["config"])

    def test_failed_login_blocks_manifest_lookup_and_deployment(self):
        result = self.run_deployment("login_failure")
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual([call["args"][0] for call in self.calls("docker")], ["login"])
        self.assertEqual(self.calls("ssh"), [])

    def test_failed_manifest_lookup_blocks_deployment(self):
        result = self.run_deployment("manifest_failure")
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual([call["args"][0] for call in self.calls("docker")], ["login", "manifest"])
        self.assertEqual(self.calls("ssh"), [])

    def test_failed_stack_update_preserves_failure_and_removes_local_auth(self):
        result = self.run_deployment("deployment_failure")
        self.assertEqual(result.returncode, 29, result.stderr)
        self.assertEqual([call["args"][0] for call in self.calls("docker")],
                         ["login", "manifest", "stack"])


if __name__ == "__main__":
    unittest.main()
