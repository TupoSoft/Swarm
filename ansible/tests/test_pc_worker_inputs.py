"""Exercise the worker's real Ansible input checks without changing a guest."""

import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


INPUT_TASKS = Path(__file__).resolve().parents[1] / "tasks" / "pc-worker-inputs.yml"
VALID_SETTINGS = {
    "pc_worker_address": "192.0.2.253/32",
    "pc_worker_vpn_cidr": "192.0.2.0/24",
    "pc_worker_manager_public_key": base64.b64encode(bytes(range(32))).decode(),
    "pc_worker_manager_endpoint": "vpn.example.com:51820",
}


class WorkerInputTests(unittest.TestCase):
    def provision_preflight(self, settings):
        with tempfile.TemporaryDirectory(prefix="pc-worker-inputs-") as directory:
            playbook = Path(directory) / "preflight.json"
            playbook.write_text(json.dumps([{
                "hosts": "localhost",
                "gather_facts": False,
                "vars": settings,
                "tasks": [{"ansible.builtin.import_tasks": str(INPUT_TASKS)}],
            }]))
            configuration = Path(directory) / "ansible.cfg"
            configuration.write_text("[defaults]\n")
            environment = dict(os.environ)
            environment.update({
                "ANSIBLE_CONFIG": str(configuration),
                "ANSIBLE_LOCAL_TEMP": str(Path(directory) / "ansible-tmp"),
                "ANSIBLE_NOCOLOR": "1",
            })
            return subprocess.run(
                ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )

    def assert_rejected(self, **changes):
        result = self.provision_preflight({**VALID_SETTINGS, **changes})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('"evaluated_to": false', result.stdout)

    def test_accepts_public_vpn_settings_without_changing_anything(self):
        result = self.provision_preflight(VALID_SETTINGS)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("changed=0", result.stdout)

    def test_requires_every_setting(self):
        settings = dict(VALID_SETTINGS)
        del settings["pc_worker_manager_public_key"]
        result = self.provision_preflight(settings)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("supply all four VPN settings", result.stdout)

    def test_rejects_configuration_injection(self):
        for field, value in [
            ("pc_worker_address", "192.0.2.253/32\nPostUp = touch /tmp/injected"),
            ("pc_worker_manager_endpoint", "vpn.example.com:51820\n"),
            ("pc_worker_manager_public_key", VALID_SETTINGS["pc_worker_manager_public_key"] + "\n"),
        ]:
            with self.subTest(field=field):
                self.assert_rejected(**{field: value})

    def test_rejects_invalid_addresses_and_prefixes(self):
        for field, value in [
            ("pc_worker_address", "192.0.2.256/32"),
            ("pc_worker_address", "192.0.2.253/24"),
            ("pc_worker_vpn_cidr", "192.0.2.0/33"),
            ("pc_worker_vpn_cidr", "192.0.2.0"),
        ]:
            with self.subTest(field=field, value=value):
                self.assert_rejected(**{field: value})

    def test_rejects_ports_outside_the_udp_range(self):
        for port in (0, 65536):
            with self.subTest(port=port):
                self.assert_rejected(pc_worker_manager_endpoint=f"vpn.example.com:{port}")

    def test_rejects_a_malformed_public_key(self):
        self.assert_rejected(pc_worker_manager_public_key="replace-me")

    def test_rejects_invalid_endpoints(self):
        for host in (
            "bad..host",
            "-vpn.example.com",
            "vpn-.example.com",
            "a" * 64 + ".example.com",
            ".".join(["a" * 63] * 4),
            "999.999.999.999",
            "192.0.2.256",
            "127.1",
            "192.000.2.1",
        ):
            with self.subTest(host=host):
                self.assert_rejected(pc_worker_manager_endpoint=f"{host}:51820")

    def test_accepts_ipv4_and_fully_qualified_dns_endpoints(self):
        for host in ("192.0.2.1", "vpn.example.com.", "a" * 63 + ".example.com"):
            with self.subTest(host=host):
                result = self.provision_preflight({
                    **VALID_SETTINGS,
                    "pc_worker_manager_endpoint": f"{host}:51820",
                })
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("changed=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
