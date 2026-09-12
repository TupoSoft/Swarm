import base64
import contextlib
import io
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "pc-worker/configure-vpn.sh"
PUBLIC_KEY = base64.b64encode(b"p" * 32).decode()
PRIVATE_KEY = base64.b64encode(b"s" * 32).decode()
ARGUMENTS = [PUBLIC_KEY, "manager.example:51820", "192.168.2.253/32", "192.168.2.0/24"]


class PcWorkerVpnTest(unittest.TestCase):
    def setUp(self):
        # Load the script's Python block without executing its privileged entry point.
        source = SCRIPT.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        self.module = {"__name__": "vpn_helper_test"}
        exec(compile(source, str(SCRIPT), "exec"), self.module)
        self.directory = tempfile.TemporaryDirectory(prefix="pc-worker-vpn-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.module["WIREGUARD_DIR"] = self.root
        self.key = self.root / "pc-swarm.key"
        self.key.write_text(PRIVATE_KEY + "\n")
        self.config = self.root / "ci-swarm-wg0.conf"
        self.root_user = self.enterContext(mock.patch.object(os, "geteuid", return_value=0))
        self.hostname = self.enterContext(mock.patch.object(self.module["socket"], "gethostname", return_value="pc-swarm-worker"))
        self.release = self.enterContext(mock.patch.object(self.module["platform"], "freedesktop_os_release", return_value={"ID": "ubuntu", "VERSION_ID": "24.04"}))
        self.virtualization = self.enterContext(mock.patch.object(subprocess, "check_output", return_value="microsoft\n"))
        self.service = self.enterContext(mock.patch.object(subprocess, "run"))

    def configure(self, arguments=None):
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.module["main"](ARGUMENTS if arguments is None else arguments)
        finally:
            self.assertNotIn(PRIVATE_KEY, output.getvalue())
            self.assertEqual(list(self.root.glob(".ci-swarm-wg0-*")), [])

    def test_creates_private_configuration_and_starts_service(self):
        self.configure()
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        settings = self.config.read_text()
        for line in ["Address = 192.168.2.253/32", f"PrivateKey = {PRIVATE_KEY}",
                     f"PublicKey = {PUBLIC_KEY}", "Endpoint = manager.example:51820",
                     "AllowedIPs = 192.168.2.0/24", "PersistentKeepalive = 25"]:
            self.assertIn(line + "\n", settings)
        self.service.assert_called_once_with(["systemctl", "enable", "--now", "wg-quick@ci-swarm-wg0"], check=True)

    def test_identical_repeat_starts_service_without_replacing_configuration(self):
        self.configure()
        inode = self.config.stat().st_ino
        self.configure()
        self.assertEqual(self.config.stat().st_ino, inode)
        self.assertEqual(self.service.call_count, 2)

    def test_changed_configuration_preserves_file_and_does_not_touch_service(self):
        self.configure()
        original = self.config.read_bytes()
        self.service.reset_mock()
        arguments = [*ARGUMENTS]
        arguments[1] = "other.example:51820"
        with self.assertRaisesRegex(ValueError, "Drain pc-swarm-worker"):
            self.configure(arguments)
        self.assertEqual(self.config.read_bytes(), original)
        self.service.assert_not_called()

    def test_invalid_inputs_fail_before_configuration_or_service_changes(self):
        invalid_values = {
            0: ["", "not-a-key", base64.b64encode(b"short").decode(), PUBLIC_KEY + "\n"],
            1: ["", "manager.example", "host:0", "host:65536", "999.1.2.3:51820", "host\nPostUp=x:51820", "[::1]:51820"],
            2: ["", "192.168.2.253", "999.1.1.1/32", "::1/128", "192.168.2.253/32\nPostUp=x"],
            3: ["", "192.168.2.0", "192.168.2.1/24", "::/0", "192.168.2.0/24\nPostUp=x"],
        }
        for index, values in invalid_values.items():
            for value in values:
                with self.subTest(index=index, value=value):
                    arguments = [*ARGUMENTS]
                    arguments[index] = value
                    with self.assertRaises(ValueError):
                        self.configure(arguments)
                    self.assertFalse(self.config.exists())
        for arguments in [[], ARGUMENTS[:3], ARGUMENTS + ["extra"]]:
            with self.assertRaisesRegex(ValueError, "usage:"):
                self.configure(arguments)
        self.virtualization.assert_not_called()
        self.service.assert_not_called()

    def test_host_guards_reject_other_machines(self):
        for target, value in [(self.root_user, 1000), (self.hostname, "development"),
                              (self.release, {"ID": "ubuntu", "VERSION_ID": "22.04"}),
                              (self.virtualization, "wsl\n")]:
            with self.subTest(value=value):
                previous = target.return_value
                target.return_value = value
                with self.assertRaises(ValueError):
                    self.configure()
                target.return_value = previous
                self.assertFalse(self.config.exists())
        self.service.assert_not_called()

    def test_missing_or_invalid_worker_key_does_not_create_configuration(self):
        self.key.unlink()
        with self.assertRaisesRegex(ValueError, "bootstrap.sh"):
            self.configure()
        self.key.write_text("invalid-private-key\n")
        with self.assertRaisesRegex(ValueError, "Worker private key"):
            self.configure()
        self.assertFalse(self.config.exists())
        self.service.assert_not_called()

    def test_failed_atomic_install_cleans_temporary_file(self):
        with mock.patch.object(os, "replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                self.configure()
        self.assertFalse(self.config.exists())
        self.service.assert_not_called()

    def test_service_failure_keeps_configuration_for_retry(self):
        self.service.side_effect = subprocess.CalledProcessError(1, ["systemctl"])
        with self.assertRaises(subprocess.CalledProcessError):
            self.configure()
        self.assertTrue(self.config.exists())
        self.service.side_effect = None
        self.configure()


if __name__ == "__main__":
    unittest.main()
