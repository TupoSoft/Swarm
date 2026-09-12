import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


RUNNER_ROOT = Path(__file__).resolve().parents[1]
OWNER = "0123456789abcdef" * 4
PREFIX = f"actions-{OWNER[:16]}"
TOKEN = "synthetic-registration-token"
PAT = "synthetic-organization-pat"


FAKE_COMMAND = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import signal
import sys
import time

name = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path(os.environ["FAKE_ROOT"])
scenario = os.environ.get("SCENARIO", "success")
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps({"name": name, "args": args, "env": {
        key: os.environ.get(key) for key in (
            "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
            "RUNNER_REGISTRATION_TOKEN", "TMPDIR", "TMP", "TEMP")}}) + "\n")

if name == "docker":
    assert args.pop(0) == "--host=unix:///var/run/docker.sock"
    command = args[0]
    if command == "inspect":
        field = args[2]
        if field == "{{.Id}}":
            print("0123456789abcdef" * 4)
        elif field == "{{.Image}}":
            print("sha256:synthetic-runner-image")
        elif field == "{{.State.Status}} {{.State.ExitCode}}":
            print("running 0" if scenario == "attach_disconnect" else
                  "exited 2" if scenario == "worker_failure" else "exited 0")
        else:
            raise AssertionError(args)
    elif command == "volume":
        if args[1] == "create":
            print(args[-1])
    elif command == "create":
        if scenario == "create_failure" and args[2].endswith("-worker"):
            sys.exit(1)
        print(args[2])
    elif command == "start":
        if "--attach" in args:
            if scenario == "attach_disconnect":
                sys.exit(1)
            if scenario == "signal":
                (root / "attach.pid").write_text(str(os.getpid()))
                print("worker attached", flush=True)
                time.sleep(60)
            print("worker completed")
    elif command == "exec":
        sys.exit(1 if scenario == "daemon_failure" else 0)
    elif command == "stop":
        if (root / "attach.pid").exists():
            try:
                os.kill(int((root / "attach.pid").read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass
    elif command == "cp":
        if scenario == "success":
            sys.exit(1)  # Normal ephemeral completion removed .runner already.
        Path(args[-1]).write_text('{"agentId": 73}')
    elif command in ("rm", "logs"):
        pass
    else:
        raise AssertionError(args)
elif name == "curl":
    method = args[args.index("-X") + 1]
    if method == "POST":
        if scenario == "registration_failure":
            sys.exit(22)
        print(json.dumps({"token": "synthetic-registration-token"}))
    elif method == "GET":
        Path(args[args.index("-o") + 1]).write_text(json.dumps({"name":
            "another-runner" if scenario == "wrong_owner" else "swarm-gh-actions-runner-0123456789abcdef"}))
        print("404" if scenario == "already_removed" else "200", end="")
    else:
        print("403" if scenario == "delete_failure" else "404", end="")
elif name == "jq":
    value = json.loads(Path(args[-1]).read_text() if args[-1].startswith("/") else sys.stdin.read())
    if "agentId" in args[1]:
        print(value["agentId"])
    elif ".name" in args[1]:
        print(value["name"])
    else:
        print(value["token"])
elif name == "runuser":
    if "./config.sh" in args and scenario == "worker_config_failure":
        sys.exit(1)
elif name in ("sleep", "chown", "chmod", "mkdir"):
    pass
else:
    raise AssertionError(name)
'''


class RunnerLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "fake"
        fake.write_text(FAKE_COMMAND)
        fake.chmod(0o755)
        for name in ("docker", "curl", "jq", "sleep", "runuser", "chown", "chmod", "mkdir"):
            (self.bin / name).symlink_to(fake)
        secret = self.root / "pat"
        secret.write_text(PAT)
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FAKE_ROOT": str(self.root),
            "GH_PAT_SECRET_FILE_PATH": str(secret),
            "RUNNER_ORG": "TupoSoft",
            "HOSTNAME": "launcher",
            "DIND_IMAGE": "docker:29.6.1-dind",
            "DIND_READY_ATTEMPTS": "2",
            "DOCKER_CONTEXT": "remote-swarm",
            "DOCKER_HOST": "ssh://synthetic-host",
            "DOCKER_TLS_VERIFY": "1",
            "DOCKER_CERT_PATH": "/synthetic-certs",
        }

    def calls(self, name=None):
        calls = [json.loads(line) for line in (self.root / "calls.jsonl").read_text().splitlines()]
        return [call for call in calls if name is None or call["name"] == name]

    def run_launcher(self, scenario="success", **env):
        result = subprocess.run(
            ["bash", str(RUNNER_ROOT / "entrypoint.sh")],
            env={**self.env, "SCENARIO": scenario, **env},
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotIn(PAT, result.stdout + result.stderr)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        return result

    def docker_args(self, command):
        return [call["args"][1:] for call in self.calls("docker") if call["args"][1] == command]

    def assert_pair_removed(self, worker=True):
        self.assertEqual(self.docker_args("rm"),
                         ([["rm", "--force", "--volumes", f"{PREFIX}-worker"]] if worker else []) +
                         [["rm", "--force", "--volumes", f"{PREFIX}-docker"]])
        self.assertEqual(self.docker_args("volume")[-1],
                         ["volume", "rm", f"{PREFIX}-work", f"{PREFIX}-socket", f"{PREFIX}-data"])
        for call in self.calls("docker"):
            self.assertNotIn("prune", call["args"])

    def test_one_job_has_private_docker_network_workspace_and_credentials(self):
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        daemon, worker = self.docker_args("create")
        self.assertIn("--privileged", daemon)
        self.assertEqual(daemon[-2:], ["dockerd", "--host=unix:///var/run/docker.sock"])
        self.assertNotIn("--privileged", worker)
        self.assertIn("container:" + PREFIX + "-docker", worker)
        self.assertEqual(worker[worker.index("--cgroupns") + 1], "private")
        for path in ("work:/actions-runner/_work", "socket:/var/run"):
            self.assertIn(f"{PREFIX}-{path}", daemon)
            self.assertIn(f"{PREFIX}-{path}", worker)
        self.assertEqual(worker[worker.index("--memory") + 1], "4g")
        self.assertEqual(worker[worker.index("--cpus") + 1], "2")
        self.assertIn("RUNNER_LABELS=swarm,ubuntu-22,docker-isolated", worker)
        self.assertNotIn("/var/run/docker.sock:/var/run/docker.sock", worker)
        self.assertNotIn("GH_PAT_SECRET_FILE_PATH", " ".join(worker))
        self.assertNotIn(PAT, " ".join(worker))
        self.assertNotIn(TOKEN, " ".join(worker))
        self.assertEqual(worker[-1], "sha256:synthetic-runner-image")
        for call in self.calls("docker"):
            for key in ("DOCKER_CONTEXT", "DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
                self.assertIsNone(call["env"][key])
        self.assert_pair_removed()

    def test_daemon_timeout_removes_resources_without_registering(self):
        result = self.run_launcher("daemon_failure")
        self.assertEqual(result.returncode, 1)
        self.assertIn("did not become ready", result.stderr)
        self.assertEqual(self.calls("curl"), [])
        self.assert_pair_removed(worker=False)

    def test_registration_failure_removes_daemon_and_volumes(self):
        result = self.run_launcher("registration_failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.docker_args("create")), 1)
        self.assert_pair_removed(worker=False)

    def test_failed_worker_creation_removes_existing_resources(self):
        result = self.run_launcher("create_failure")
        self.assertNotEqual(result.returncode, 0)
        self.assert_pair_removed(worker=False)

    def test_failed_worker_removes_its_registration_and_preserves_failure(self):
        result = self.run_launcher("worker_failure")
        self.assertEqual(result.returncode, 2, result.stderr)
        delete = self.calls("curl")[-1]["args"]
        self.assertEqual(delete[delete.index("-X") + 1], "DELETE")
        self.assertEqual(delete[-1], "https://api.github.com/orgs/TupoSoft/actions/runners/73")
        self.assert_pair_removed()

    def test_registration_removal_failure_does_not_skip_resource_cleanup(self):
        result = self.run_launcher("delete_failure")
        self.assertEqual(result.returncode, 1)
        self.assertIn("403", result.stderr)
        self.assert_pair_removed()

    def test_worker_cannot_delete_another_runner_by_editing_metadata(self):
        result = self.run_launcher("wrong_owner")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ownership-mismatch", result.stderr)
        self.assertFalse(any("DELETE" in call["args"] for call in self.calls("curl")))
        self.assert_pair_removed()

    def test_already_removed_registration_does_not_require_delete(self):
        result = self.run_launcher("already_removed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any("DELETE" in call["args"] for call in self.calls("curl")))
        self.assert_pair_removed()

    def test_attachment_disconnect_cannot_report_running_worker_as_success(self):
        result = self.run_launcher("attach_disconnect")
        self.assertEqual(result.returncode, 1)
        self.assertIn("before the worker exited", result.stderr)
        self.assert_pair_removed()

    def test_repository_scope_and_resource_overrides(self):
        result = self.run_launcher(RUNNER_REPO="TupoSoft/LeadEmailFinder", RUNNER_MEMORY="6g",
                                   RUNNER_CPUS="3", DIND_MEMORY="5g", DIND_CPUS="4")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("curl")[0]["args"][-1],
                         "https://api.github.com/repos/TupoSoft/LeadEmailFinder/actions/runners/registration-token")
        daemon, worker = self.docker_args("create")
        self.assertEqual(daemon[daemon.index("--memory") + 1], "5g")
        self.assertEqual(worker[worker.index("--memory") + 1], "6g")
        self.assertEqual(worker[worker.index("--cpus") + 1], "3")

    def test_signal_stops_worker_and_removes_only_its_pair(self):
        process = subprocess.Popen(["bash", str(RUNNER_ROOT / "entrypoint.sh")],
                                   env={**self.env, "SCENARIO": "signal"},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "attach.pid").exists():
                self.assertIsNone(process.poll(), "launcher exited before attaching")
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 143, stdout + stderr)
            self.assert_pair_removed()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def run_worker(self, scenario="success"):
        bash_env = self.root / "bash-env"
        bash_env.write_text('cd() { builtin cd "$FAKE_ROOT"; }\n')
        return subprocess.run(["bash", str(RUNNER_ROOT / "runner-entrypoint.sh")],
                              env={**self.env, "SCENARIO": scenario, "BASH_ENV": str(bash_env),
                                   "RUNNER_REGISTRATION_TOKEN": TOKEN,
                                   "RUNNER_URL": "https://github.com/TupoSoft",
                                   "RUNNER_NAME": "test-worker"},
                              text=True, capture_output=True, timeout=5)

    def test_worker_is_ephemeral_and_listener_does_not_inherit_registration_token(self):
        result = self.run_worker()
        self.assertEqual(result.returncode, 0, result.stderr)
        config, listener = self.calls("runuser")
        self.assertIn("--ephemeral", config["args"])
        self.assertNotIn("--replace", config["args"])
        self.assertNotIn("--disableupdate", config["args"])
        self.assertEqual(listener["args"], ["-u", "runner", "--", "./run.sh"])
        self.assertIsNone(listener["env"]["RUNNER_REGISTRATION_TOKEN"])
        self.assertIsNone(listener["env"]["DOCKER_HOST"])
        self.assertIsNone(listener["env"]["DOCKER_CONTEXT"])
        for call in (config, listener):
            for key in ("TMPDIR", "TMP", "TEMP"):
                self.assertEqual(call["env"][key], "/actions-runner/_work/_temp")

    def test_worker_configuration_failure_does_not_start_listener(self):
        result = self.run_worker("worker_config_failure")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.calls("runuser")), 1)


if __name__ == "__main__":
    unittest.main()
