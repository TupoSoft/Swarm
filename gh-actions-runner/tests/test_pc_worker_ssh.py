import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "pc-worker/ansible-playbook-wsl"


class PcWorkerSshTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pc-worker-ssh-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / "bin with spaces"
        self.bin.mkdir()
        self.calls = self.root / "ansible-arguments.json"
        ansible = self.bin / "ansible-playbook"
        ansible.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                           "from pathlib import Path\n"
                           "Path(os.environ['TEST_ANSIBLE_CALL']).write_text(json.dumps(sys.argv[1:]))\n")
        ansible.chmod(0o755)
        self.state = self.root / "Windows VM state"
        self.source = self.state / "machines/default/hyperv/private_key"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("synthetic private key version one\n")
        self.source.chmod(0o777)
        self.target = self.root / 'Linux cache with "quotes"' / "private key"
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "TEST_ANSIBLE_CALL": str(self.calls),
                    "VAGRANT_DOTFILE_PATH": str(self.state),
                    "PC_WORKER_SSH_KEY_PATH": str(self.target)}

    def run_adapter(self, *arguments, env=None):
        result = subprocess.run([str(SCRIPT), *arguments], env=env or self.env,
                                text=True, capture_output=True)
        self.assertNotIn("synthetic private key", result.stdout + result.stderr)
        return result

    def test_copies_key_privately_and_preserves_argument_boundaries(self):
        arguments = ["--inventory", "inventory with spaces", "--extra-vars", '{"name":"worker one"}',
                     "playbook with spaces.yml"]
        result = self.run_adapter(*arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(self.calls.read_text())
        self.assertEqual(actual[:-2], arguments)
        self.assertEqual(actual[-2], "--extra-vars")
        self.assertEqual(json.loads(actual[-1]), {"ansible_ssh_private_key_file": str(self.target)})
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.target.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.source.stat().st_mode), 0o777)

    def test_rerun_refreshes_rotated_key_and_repairs_cache_permissions(self):
        self.assertEqual(self.run_adapter("worker.yml").returncode, 0)
        self.source.write_text("synthetic private key version two\n")
        self.target.chmod(0o644)
        self.target.parent.chmod(0o755)
        result = self.run_adapter("worker.yml")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.target.parent.stat().st_mode), 0o700)
        self.assertEqual(list(self.target.parent.iterdir()), [self.target])

    def test_version_does_not_need_vm_state(self):
        env = {key: value for key, value in self.env.items()
               if key not in {"VAGRANT_DOTFILE_PATH", "PC_WORKER_SSH_KEY_PATH"}}
        result = self.run_adapter("--version", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.calls.read_text()), ["--version"])
        self.assertFalse(self.target.exists())

    def test_missing_key_stops_before_ansible_or_cache_creation(self):
        self.source.unlink()
        result = self.run_adapter("worker.yml")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("start the worker VM first", result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.target.parent.exists())

    def test_relative_paths_are_rejected(self):
        for variable in ["VAGRANT_DOTFILE_PATH", "PC_WORKER_SSH_KEY_PATH"]:
            with self.subTest(variable=variable):
                result = self.run_adapter("worker.yml", env={**self.env, variable: "relative/path"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("absolute paths", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_windows_filesystem_is_rejected_before_copying_key(self):
        findmnt = self.bin / "findmnt"
        findmnt.write_text("#!/bin/sh\nprintf '9p\\n'\n")
        findmnt.chmod(0o755)
        result = self.run_adapter("worker.yml")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Linux filesystem", result.stderr)
        self.assertFalse(self.target.parent.exists())
        self.assertFalse(self.calls.exists())

    def test_symlink_destination_does_not_overwrite_another_file(self):
        self.target.parent.mkdir()
        unrelated = self.root / "another key"
        unrelated.write_text("preserve this file")
        self.target.symlink_to(unrelated)
        result = self.run_adapter("worker.yml")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(unrelated.read_text(), "preserve this file")
        self.assertFalse(self.calls.exists())

    def test_unenforced_permissions_stop_before_ansible_and_remove_temporary_key(self):
        loader = importlib.machinery.SourceFileLoader("pc_worker_ssh_adapter", str(SCRIPT))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        with mock.patch.object(sys, "path", [str(SCRIPT.parent), *sys.path]):
            loader.exec_module(module)
        self.target.parent.mkdir(mode=0o755)
        with mock.patch.dict(os.environ, self.env), mock.patch.object(module.sys, "argv", [str(SCRIPT), "worker.yml"]), \
                mock.patch.object(Path, "chmod"), mock.patch.object(module.os, "execv") as execute:
            with self.assertRaisesRegex(ValueError, "cannot enforce private permissions"):
                module.main()
        execute.assert_not_called()
        self.assertEqual(list(self.target.parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
