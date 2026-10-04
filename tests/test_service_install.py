# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validate installation files without changing the real user's service manager."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def test_installer_quotes_checkout_and_writes_login_hook(tmp_path):
    checkout = tmp_path / 'checkout with spaces % and $'
    (checkout / 'scripts').mkdir(parents=True)
    (checkout / 'packaging/systemd').mkdir(parents=True)
    for script in ('install-service', 'start-service'):
        shutil.copy2(ROOT / 'scripts' / script, checkout / 'scripts' / script)
    shutil.copy2(ROOT / 'packaging/systemd/universal-input.service.in', checkout / 'packaging/systemd')
    config = tmp_path / 'config'
    subprocess.run([str(checkout / 'scripts/install-service'), '--no-start'], env={**os.environ, 'XDG_CONFIG_HOME': str(config)}, check=True)
    unit = config / 'systemd/user/universal-input.service'
    login = config / 'autostart/universal-input.desktop'
    text = unit.read_text()
    assert '@CHECKOUT@' not in text
    assert 'checkout with spaces %% and $' in text
    assert 'Restart=on-failure' in text
    assert 'WantedBy=default.target' in text
    assert 'scripts/start-service' in login.read_text()
    assert not (config / 'systemd/user/default.target.wants').exists()
    if shutil.which('systemd-analyze'):
        subprocess.run(['systemd-analyze', '--user', 'verify', str(unit)], check=True)
    if shutil.which('desktop-file-validate'):
        subprocess.run(['desktop-file-validate', str(login)], check=True)


def test_login_hook_imports_display_before_start_and_rejects_wayland(tmp_path):
    log = tmp_path / 'calls.jsonl'
    fake = tmp_path / 'systemctl'
    fake.write_text('#!/usr/bin/python3\nimport json, os, sys\nwith open(os.environ["CALL_LOG"], "a") as f: f.write(json.dumps(sys.argv[1:]) + "\\n")\n')
    fake.chmod(0o755)
    env = {**os.environ, 'PATH': str(tmp_path), 'CALL_LOG': str(log), 'DISPLAY': ':88', 'XDG_SESSION_TYPE': 'x11'}
    subprocess.run([str(ROOT / 'scripts/start-service')], env=env, check=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls[0][:2] == ['--user', 'import-environment'] and 'DISPLAY' in calls[0]
    assert calls[1] == ['--user', 'reset-failed', 'universal-input.service']
    assert calls[2] == ['--user', 'start', 'universal-input.service']
    log.unlink()
    result = subprocess.run([str(ROOT / 'scripts/start-service')], env={**env, 'XDG_SESSION_TYPE': 'wayland'}, capture_output=True)
    assert result.returncode != 0 and not log.exists()
