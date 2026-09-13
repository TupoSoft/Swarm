"""Exercise WSL launcher boundaries without calling Windows or starting a VM."""

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


LAUNCHER = Path(__file__).resolve().parents[1] / "pc-worker" / "vagrant-wsl"
loader = importlib.machinery.SourceFileLoader("vagrant_wsl", str(LAUNCHER))
spec = importlib.util.spec_from_loader(loader.name, loader)
launcher = importlib.util.module_from_spec(spec)
with patch.object(sys, "path", [str(LAUNCHER.parent), *sys.path]):
    loader.exec_module(launcher)


class EnvironmentTests(unittest.TestCase):
    def output(self, command, env):
        if command[0] == "powershell.exe":
            self.assertIn("$env:USERPROFILE", command[-1])
            return r"C:\Users\A Person"
        if command[:2] == ["wslpath", "-u"]:
            return "/mnt/c/Users/A Person"
        if command[:2] == ["wslpath", "-w"]:
            return "C:\\" + command[2].removeprefix("/mnt/c/").replace("/", "\\")
        self.fail(f"Unexpected command: {command}")

    def test_defaults_keep_vagrant_state_on_windows_and_keys_in_linux(self):
        with patch.object(launcher, "output", side_effect=self.output), patch.object(
            launcher.Path, "home", return_value=Path("/home/developer")
        ):
            env = launcher.prepare_environment({"PATH": "/usr/bin"})
        self.assertEqual(env["VAGRANT_HOME"], "/mnt/c/Users/A Person/.vagrant.d")
        self.assertEqual(
            env["VAGRANT_DOTFILE_PATH"], "/mnt/c/Users/A Person/Vagrant/SwarmWorker/.vagrant"
        )
        self.assertEqual(
            env["PC_WORKER_SSH_KEY_PATH"],
            "/home/developer/.local/share/swarm-pc-worker/ssh/private_key",
        )
        self.assertEqual(env["VAGRANT_WSL_ENABLE_WINDOWS_ACCESS"], "1")
        self.assertEqual(env["VAGRANT_PREFERRED_POWERSHELL"], "powershell")
        self.assertEqual(env["VAGRANT_DEFAULT_PROVIDER"], "hyperv")
        self.assertTrue(env["PATH"].startswith("/usr/bin:"))
        self.assertIn("/mnt/c/Program Files/Vagrant/bin", env["PATH"])

    def test_explicit_windows_locations_and_key_are_preserved(self):
        source = {
            "VAGRANT_HOME": "/mnt/c/vagrant-home",
            "VAGRANT_DOTFILE_PATH": "/mnt/c/state with spaces",
            "PC_WORKER_SSH_KEY_PATH": "/home/developer/my key",
        }
        with patch.object(launcher, "output", side_effect=self.output) as run:
            env = launcher.prepare_environment(source)
        for name, value in source.items():
            self.assertEqual(env[name], value)
        self.assertTrue(all(call.args[0][0] == "wslpath" for call in run.call_args_list))

    def test_linux_and_unc_storage_are_rejected(self):
        for path in (r"\\wsl.localhost\Ubuntu\tmp\state", r"\\server\share\state"):
            with self.subTest(path=path), patch.object(launcher, "output", return_value=path):
                with self.assertRaisesRegex(launcher.LauncherError, "must be on a Windows drive"):
                    launcher.windows_storage_path("VAGRANT_DOTFILE_PATH", "/tmp/state", {})

    def test_provider_environment_rejects_other_providers(self):
        with self.assertRaisesRegex(launcher.LauncherError, "Hyper-V provider only"):
            launcher.prepare_environment({"VAGRANT_DEFAULT_PROVIDER": "libvirt"})


class InvocationTests(unittest.TestCase):
    def test_provider_arguments_are_checked_until_ssh_argument_separator(self):
        for arguments in (["up", "--provider=libvirt"], ["up", "--provider", "virtualbox"]):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(launcher.LauncherError, "Hyper-V provider only"):
                    launcher.check_provider(arguments)
        launcher.check_provider(["up", "--provider", "hyperv"])
        launcher.check_provider(["ssh", "--", "--provider=anything"])

    def test_windows_vagrant_is_rejected_before_running_it(self):
        with patch.object(launcher.shutil, "which", return_value="/mnt/c/Vagrant/bin/vagrant"), patch.object(
            launcher, "output", return_value=r"C:\Vagrant\bin\vagrant"
        ) as run:
            with self.assertRaisesRegex(launcher.LauncherError, "selected vagrant is on Windows"):
                launcher.linux_vagrant({"PATH": "/usr/bin"})
        self.assertEqual(run.call_count, 1)

    def test_old_linux_vagrant_is_rejected(self):
        with patch.object(launcher.shutil, "which", return_value="/usr/bin/vagrant"), patch.object(
            launcher, "output", side_effect=[r"\\wsl.localhost\Ubuntu\usr\bin\vagrant", "Vagrant 2.4.8"]
        ):
            with self.assertRaisesRegex(launcher.LauncherError, "2.4.9 or newer"):
                launcher.linux_vagrant({})

    def test_linux_vagrant_is_executed_with_exact_arguments_and_environment(self):
        arguments = ["ssh", "--", "printf '%s' 'value with spaces; $(touch /tmp/never)'", ""]
        env = {"PATH": "/usr/bin", "VAGRANT_WSL_ENABLE_WINDOWS_ACCESS": "1"}
        with patch.dict(launcher.os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}), patch.object(
            launcher.platform, "system", return_value="Linux"
        ), patch.object(launcher, "prepare_environment", return_value=env), patch.object(
            launcher, "linux_vagrant", return_value="/usr/bin/vagrant"
        ), patch.object(launcher, "check_network") as network, patch.object(
            launcher, "prepare_ssh_key"
        ) as key, patch.object(
            launcher.os, "chdir"
        ) as chdir, patch.object(launcher.os, "execve") as execute:
            self.assertEqual(launcher.main(arguments), 0)
        network.assert_called_once_with(env)
        key.assert_called_once_with(env)
        chdir.assert_called_once_with(LAUNCHER.parent)
        execute.assert_called_once_with("/usr/bin/vagrant", ["/usr/bin/vagrant", *arguments], env)

    def test_static_commands_skip_network_preflight(self):
        for arguments in (["validate"], ["status"], ["help"], ["--version"], ["up", "--help"], []):
            with self.subTest(arguments=arguments):
                self.assertFalse(launcher.needs_network(arguments))
        for command in ("up", "reload", "resume", "provision", "ssh"):
            self.assertTrue(launcher.needs_network(["--debug", command]))
        self.assertTrue(launcher.needs_network(["ssh", "--", "-v"]))


class SSHKeyTests(unittest.TestCase):
    def test_existing_generated_key_is_refreshed_before_each_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            generated = state / "machines/default/hyperv/private_key"
            generated.parent.mkdir(parents=True)
            generated.write_text("test key")
            copied_key = Path(directory) / "linux-key"
            env = {
                "VAGRANT_DOTFILE_PATH": str(state),
                "PC_WORKER_VAGRANT_SSH_KEY": "/old/key",
            }
            with patch.object(launcher, "copy_vagrant_key", return_value=copied_key) as copy:
                launcher.prepare_ssh_key(env)
                self.assertEqual(env["PC_WORKER_VAGRANT_SSH_KEY"], str(copied_key))
                generated.write_text("replacement test key")
                launcher.prepare_ssh_key(env)
            self.assertEqual(copy.call_count, 2)
            self.assertEqual(env["PC_WORKER_VAGRANT_SSH_KEY"], str(copied_key))

    def test_missing_generated_key_does_not_select_a_stale_linux_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            old_key = Path(directory) / "old-key"
            old_key.write_text("test key")
            env = {
                "VAGRANT_DOTFILE_PATH": str(Path(directory) / "state"),
                "PC_WORKER_VAGRANT_SSH_KEY": str(old_key),
                "PC_WORKER_SSH_KEY_PATH": str(old_key),
            }
            with patch.object(launcher, "copy_vagrant_key") as copy:
                launcher.prepare_ssh_key(env)
            copy.assert_not_called()
            self.assertNotIn("PC_WORKER_VAGRANT_SSH_KEY", env)

    def test_key_copy_failure_becomes_a_user_facing_launcher_error(self):
        with patch.object(launcher.Path, "is_file", return_value=True), patch.object(
            launcher, "copy_vagrant_key", side_effect=ValueError("SSH key must be in Linux storage")
        ):
            with self.assertRaisesRegex(launcher.LauncherError, "Cannot prepare the Vagrant SSH key"):
                launcher.prepare_ssh_key({"VAGRANT_DOTFILE_PATH": "/mnt/c/state"})


class NetworkTests(unittest.TestCase):
    def check(self, route, default="eth0", link_state="UP", addresses=None):
        addresses = addresses or {"IPAddress": "172.18.240.1", "PrefixLength": 20}

        def output(command, env):
            if command == ["ip", "-j", "route", "show", "default"]:
                return json.dumps([{"dev": default, "gateway": "172.27.16.1"}])
            if command == ["ip", "-j", "route", "get", "172.18.240.1"]:
                return json.dumps([route])
            if command == ["ip", "-j", "link", "show", "dev", route["dev"]]:
                return json.dumps([{"operstate": link_state}])
            self.fail(f"Unexpected command: {command}")

        with patch.object(launcher, "powershell", return_value=json.dumps(addresses)), patch.object(
            launcher, "output", side_effect=output
        ):
            launcher.check_network({})

    def test_default_switch_docker_overlap_is_rejected(self):
        for device in ("br-205791d95041", "docker0"):
            with self.subTest(device=device):
                with self.assertRaisesRegex(launcher.LauncherError, "172.18.240.0/20.*Docker.*" + device):
                    self.check({"dev": device, "dst": "172.18.240.1"})

    def test_inactive_nondefault_route_is_rejected(self):
        with self.assertRaisesRegex(launcher.LauncherError, "inactive route through old-bridge"):
            self.check({"dev": "old-bridge"}, link_state="DOWN")

    def test_route_through_wsl_gateway_passes(self):
        self.check({"dev": "eth0", "gateway": "172.27.16.1"})

    def test_active_nondefault_route_is_allowed(self):
        self.check({"dev": "vpn0"}, link_state="UP")


if __name__ == "__main__":
    unittest.main()
