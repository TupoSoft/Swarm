"""Run inside the image build; the bootstrap host may still have older Git."""

from pathlib import Path
import subprocess
import tempfile
import unittest


class GitCapabilitiesTest(unittest.TestCase):
    def test_deleted_blob_remains_readable_through_nul_delimited_history(self):
        with tempfile.TemporaryDirectory(prefix="runner-git-check-") as directory:
            root = Path(directory)

            def git(*args, input=None):
                return subprocess.run(
                    ["git", *args], cwd=root, input=input,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                ).stdout

            def commit(message):
                git("add", "--all")
                git("-c", "user.name=Runner image check",
                    "-c", "user.email=runner-check@example.invalid",
                    "commit", "--quiet", "--message", message)

            git("init", "--quiet")
            historical_path = "retired/session.txt"
            historical_content = b"synthetic historical content\n"
            fixture = root / historical_path
            fixture.parent.mkdir()
            fixture.write_bytes(historical_content)
            commit("add historical fixture")
            object_id = git("rev-parse", f"HEAD:{historical_path}").strip()

            fixture.unlink()
            (root / "clean.txt").write_text("The current tree is clean.\n")
            commit("remove historical fixture")

            inventory = git("rev-list", "--objects", "--all", "-z")
            self.assertTrue(
                inventory.endswith(b"\0"),
                "Git must support NUL-delimited rev-list output (Git >= 2.50).",
            )
            records = inventory.split(b"\0")
            self.assertIn(object_id, records)
            self.assertEqual(records[records.index(object_id) + 1],
                             b"path=" + historical_path.encode())

            batch = git("cat-file", "--batch", input=object_id + b"\n")
            expected_header = object_id + f" blob {len(historical_content)}\n".encode()
            self.assertEqual(batch, expected_header + historical_content + b"\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
