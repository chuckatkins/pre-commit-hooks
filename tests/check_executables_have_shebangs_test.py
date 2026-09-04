from __future__ import annotations

import os
import sys

import pytest

from pre_commit_hooks import check_executables_have_shebangs
from pre_commit_hooks.check_executables_have_shebangs import main
from pre_commit_hooks.util import cmd_output

skip_win32 = pytest.mark.skipif(
    sys.platform == 'win32',
    reason="non-git checks aren't relevant on windows",
)


@skip_win32  # pragma: win32 no cover
@pytest.mark.parametrize(
    'content', (
        b'#!/bin/bash\nhello world\n',
        b'#!/usr/bin/env python3.6',
        b'#!python',
        '#!☃'.encode(),
    ),
)
def test_has_shebang(content, tmpdir):
    path = tmpdir.join('path')
    path.write(content, 'wb')
    assert main((str(path),)) == 0


@pytest.mark.parametrize(
    ('content', 'expected'), (
        (b'#!/usr/bin/env python\n', True),
        (b'#!/usr/bin/env -S python -O\n', True),
        (b'#!/bin/env bash\n', False),
        (b'#!/bin/bash\n', False),
        (b'#!/usr/bin/env\n', False),
    ),
)
def test_require_env_shebang(content, expected, tmpdir):
    path = tmpdir.join('path')
    path.write(content, 'wb')
    assert check_executables_have_shebangs.has_shebang(
        str(path), require_env=True,
    ) is expected


@pytest.mark.parametrize(
    ('content', 'expected'), (
        (b'#!/bin/bash\necho hi\n', b'#!/usr/bin/env bash\necho hi\n'),
        (
            b'#!/opt/bin/python -O\nprint("hi")\n',
            b'#!/usr/bin/env -S python -O\nprint("hi")\n',
        ),
        (b'#!/bin/env bash\necho hi\n', b'#!/usr/bin/env bash\necho hi\n'),
    ),
)
def test_require_env_fix(content, expected, tmpdir, capsys):
    path = tmpdir.join('path')
    path.write(content, 'wb')

    assert check_executables_have_shebangs._check_executable(
        str(path), require_env=True, fix=True,
    ) == 1
    stdout, stderr = capsys.readouterr()
    assert stdout == f'Fixing {path}\n'
    assert stderr == ''
    assert path.read('rb') == expected

    assert check_executables_have_shebangs._check_executable(
        str(path), require_env=True, fix=True,
    ) == 0


@pytest.mark.parametrize(
    'content', (b'echo hi\n', b'#!\n', b'#!/\n', b'#!/bin/env\n'),
)
def test_require_env_fix_cannot_infer_interpreter(content, tmpdir):
    path = tmpdir.join('path')
    path.write(content, 'wb')

    assert check_executables_have_shebangs._check_executable(
        str(path), require_env=True, fix=True,
    ) == 1
    assert path.read('rb') == content


def test_fix_requires_require_env():
    with pytest.raises(SystemExit) as excinfo:
        main(('--fix',))
    assert excinfo.value.code == 2


@skip_win32  # pragma: win32 no cover
@pytest.mark.parametrize(
    'content', (
        b'',
        b' #!python\n',
        b'\n#!python\n',
        b'python\n',
        '☃'.encode(),
    ),
)
def test_bad_shebang(content, tmpdir, capsys):
    path = tmpdir.join('path')
    path.write(content, 'wb')
    assert main((str(path),)) == 1
    _, stderr = capsys.readouterr()
    assert stderr.startswith(f'{path}: marked executable but')


def test_check_git_filemode_passing(tmpdir):
    with tmpdir.as_cwd():
        cmd_output('git', 'init', '.')

        f = tmpdir.join('f')
        f.write('#!/usr/bin/env bash')
        f_path = str(f)
        cmd_output('chmod', '+x', f_path)
        cmd_output('git', 'add', f_path)
        cmd_output('git', 'update-index', '--chmod=+x', f_path)

        g = tmpdir.join('g').ensure()
        g_path = str(g)
        cmd_output('git', 'add', g_path)

        # this is potentially a problem, but not something the script intends
        # to check for -- we're only making sure that things that are
        # executable have shebangs
        h = tmpdir.join('h')
        h.write('#!/usr/bin/env bash')
        h_path = str(h)
        cmd_output('git', 'add', h_path)

        files = (f_path, g_path, h_path)
        assert check_executables_have_shebangs._check_git_filemode(files) == 0


def test_check_git_filemode_passing_unusual_characters(tmpdir):
    with tmpdir.as_cwd():
        cmd_output('git', 'init', '.')

        f = tmpdir.join('mañana.txt')
        f.write('#!/usr/bin/env bash')
        f_path = str(f)
        cmd_output('chmod', '+x', f_path)
        cmd_output('git', 'add', f_path)
        cmd_output('git', 'update-index', '--chmod=+x', f_path)

        files = (f_path,)
        assert check_executables_have_shebangs._check_git_filemode(files) == 0


def test_check_git_filemode_failing(tmpdir):
    with tmpdir.as_cwd():
        cmd_output('git', 'init', '.')

        f = tmpdir.join('f').ensure()
        f_path = str(f)
        cmd_output('chmod', '+x', f_path)
        cmd_output('git', 'add', f_path)
        cmd_output('git', 'update-index', '--chmod=+x', f_path)

        files = (f_path,)
        assert check_executables_have_shebangs._check_git_filemode(files) == 1


def test_check_git_filemode_require_env(tmpdir):
    with tmpdir.as_cwd():
        cmd_output('git', 'init', '.')

        f = tmpdir.join('f')
        f.write('#!/bin/bash')
        f_path = str(f)
        cmd_output('git', 'add', f_path)
        cmd_output('git', 'update-index', '--chmod=+x', f_path)

        files = (f_path,)
        assert check_executables_have_shebangs._check_git_filemode(files) == 0
        assert check_executables_have_shebangs._check_git_filemode(
            files, require_env=True,
        ) == 1


@pytest.mark.parametrize(
    ('content', 'mode', 'expected'),
    (
        pytest.param('#!python', '+x', 0, id='shebang with executable'),
        pytest.param('#!python', '-x', 0, id='shebang without executable'),
        pytest.param('', '+x', 1, id='no shebang with executable'),
        pytest.param('', '-x', 0, id='no shebang without executable'),
    ),
)
def test_git_executable_shebang(temp_git_dir, content, mode, expected):
    with temp_git_dir.as_cwd():
        path = temp_git_dir.join('path')
        path.write(content)
        cmd_output('git', 'add', str(path))
        cmd_output('chmod', mode, str(path))
        cmd_output('git', 'update-index', f'--chmod={mode}', str(path))

        # simulate how identify chooses that something is executable
        filenames = [path for path in [str(path)] if os.access(path, os.X_OK)]

        assert main(filenames) == expected
