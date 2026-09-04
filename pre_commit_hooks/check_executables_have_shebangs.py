"""Check that executable text files have a shebang."""
from __future__ import annotations

import argparse
import shlex
import sys
from collections.abc import Generator
from collections.abc import Sequence
from typing import NamedTuple

from pre_commit_hooks.util import cmd_output
from pre_commit_hooks.util import zsplit

EXECUTABLE_VALUES = frozenset(('1', '3', '5', '7'))


def check_executables(
        paths: list[str], *, require_env: bool = False, fix: bool = False,
) -> int:
    fs_tracks_executable_bit = cmd_output(
        'git', 'config', 'core.fileMode', retcode=None,
    ).strip()
    if fs_tracks_executable_bit == 'false':  # pragma: win32 cover
        return _check_git_filemode(
            paths, require_env=require_env, fix=fix,
        )
    else:  # pragma: win32 no cover
        retv = 0
        for path in paths:
            retv |= _check_executable(
                path, require_env=require_env, fix=fix,
            )

        return retv


class GitLsFile(NamedTuple):
    mode: str
    filename: str


def git_ls_files(paths: Sequence[str]) -> Generator[GitLsFile]:
    outs = cmd_output('git', 'ls-files', '-z', '--stage', '--', *paths)
    for out in zsplit(outs):
        metadata, filename = out.split('\t')
        mode, _, _ = metadata.split()
        yield GitLsFile(mode, filename)


def _check_git_filemode(
        paths: Sequence[str], *, require_env: bool = False, fix: bool = False,
) -> int:
    seen: set[str] = set()
    for ls_file in git_ls_files(paths):
        is_executable = any(b in EXECUTABLE_VALUES for b in ls_file.mode[-3:])
        if is_executable and _check_executable(
                ls_file.filename, require_env=require_env, fix=fix,
        ):
            seen.add(ls_file.filename)

    return int(bool(seen))


def has_shebang(path: str, *, require_env: bool = False) -> bool:
    with open(path, 'rb') as f:
        first_bytes = f.read(2)
        if first_bytes != b'#!':
            return False
        elif not require_env:
            return True
        else:
            cmd = f.readline().split()

    return (
        len(cmd) >= 2 and
        cmd[0] == b'/usr/bin/env'
    )


def _fix_shebang(path: str) -> bool:
    with open(path, 'rb+') as f:
        first_line = f.readline()
        if not first_line.startswith(b'#!'):
            return False

        line = first_line.rstrip(b'\r\n')
        newline = first_line[len(line):]
        command = line[2:].strip()
        cmd = command.split(maxsplit=1)
        if not cmd:
            return False

        executable = cmd[0].rsplit(b'/', 1)[-1]
        if not executable or (executable == b'env' and len(cmd) == 1):
            return False

        if executable == b'env':
            new_first_line = b'#!/usr/bin/env ' + cmd[1] + newline
        elif len(cmd) == 2:
            new_first_line = (
                b'#!/usr/bin/env -S ' + executable + b' ' + cmd[1] + newline
            )
        else:
            new_first_line = b'#!/usr/bin/env ' + executable + newline

        rest = f.read()
        f.seek(0)
        f.write(new_first_line)
        f.write(rest)
        f.truncate()

    return True


def _check_executable(
        path: str, *, require_env: bool, fix: bool,
) -> int:
    if has_shebang(path, require_env=require_env):
        return 0
    elif fix and _fix_shebang(path):
        print(f'Fixing {path}')
    else:
        _message(path, require_env=require_env)

    return 1


def _message(path: str, *, require_env: bool = False) -> None:
    if require_env:
        problem = 'does not have a /usr/bin/env shebang'
        suggestion = (
            'use a /usr/bin/env shebang (e.g. `#!/usr/bin/env python`)'
        )
    else:
        problem = 'has no (or invalid) shebang'
        suggestion = 'double-check its shebang'

    print(
        f'{path}: marked executable but {problem}!\n'
        f"  If it isn't supposed to be executable, try: "
        f'`chmod -x {shlex.quote(path)}`\n'
        f'  If on Windows, you may also need to: '
        f'`git add --chmod=-x {shlex.quote(path)}`\n'
        f'  If it is supposed to be executable, {suggestion}.',
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--require-env', action='store_true',
        help='Require shebangs to invoke an interpreter through /usr/bin/env',
    )
    parser.add_argument(
        '--fix', action='store_true',
        help=(
            'Rewrite existing shebangs to use /usr/bin/env '
            '(requires --require-env)'
        ),
    )
    parser.add_argument('filenames', nargs='*')
    args = parser.parse_args(argv)
    if args.fix and not args.require_env:
        parser.error('--fix requires --require-env')

    return check_executables(
        args.filenames,
        require_env=args.require_env,
        fix=args.fix,
    )


if __name__ == '__main__':
    raise SystemExit(main())
