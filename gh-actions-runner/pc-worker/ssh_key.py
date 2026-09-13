"""Maintain a private Linux copy of the current Vagrant machine's SSH key."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile


def copy_vagrant_key(environment):
    state = Path(environment.get("VAGRANT_DOTFILE_PATH", ""))
    target = Path(environment.get("PC_WORKER_SSH_KEY_PATH", ""))
    if not state.is_absolute() or not target.is_absolute():
        raise ValueError("VAGRANT_DOTFILE_PATH and PC_WORKER_SSH_KEY_PATH must be absolute paths.")
    source = state / "machines/default/hyperv/private_key"
    if not source.is_file():
        raise ValueError("The Vagrant SSH key is missing; start the worker VM first.")
    ancestor = target.parent.resolve()
    while not ancestor.exists():
        ancestor = ancestor.parent
    filesystem = subprocess.check_output(
        ["findmnt", "--noheadings", "--output", "FSTYPE", "--target", str(ancestor)],
        env=environment, text=True).strip()
    if filesystem in {"9p", "drvfs", "ntfs", "ntfs3", "fuseblk", "cifs", "smb3", "vfat"}:
        raise ValueError("PC_WORKER_SSH_KEY_PATH must be on the Linux filesystem.")
    if target.is_symlink():
        raise ValueError("PC_WORKER_SSH_KEY_PATH must not be a symbolic link.")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(source.read_bytes())
        temporary.chmod(0o600)
        if (stat.S_IMODE(target.parent.stat().st_mode), stat.S_IMODE(temporary.stat().st_mode)) != (0o700, 0o600):
            raise ValueError("The Linux SSH key cache cannot enforce private permissions.")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target
