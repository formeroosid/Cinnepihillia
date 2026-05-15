# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import os
import getpass
import pwd
import grp


def ensure_dir_permissions(out_dir):
    """Create directory and set ownership to the current user with 775."""
    os.makedirs(out_dir, exist_ok=True)
    user = getpass.getuser()
    uid = pwd.getpwnam(user).pw_uid
    gid = grp.getgrnam(user).gr_gid
    os.chown(out_dir, uid, gid)
    os.chmod(out_dir, 0o775)
