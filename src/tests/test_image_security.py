import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('verify_airgap', Path(__file__).resolve().parents[2] / 'scripts/verify_airgap.py')
airgap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(airgap)


def image(tmp_path):
    root = tmp_path / 'rootfs'
    root.mkdir()
    files = {
        'etc/shadow': 'root:!:0:0:99999:7:::\n',
        'etc/inittab': '::sysinit:/etc/init.d/rcS\n',
        'etc/nftables.conf': 'table inet filter {\n' + '\n'.join('chain ' + c + ' { type filter hook ' + c + ' priority 0; policy drop; }' for c in ('input', 'output', 'forward')) + '\n}',
        'etc/udev/rules.d/99-seedcash-usb-deny.rules': 'ACTION=="add", SUBSYSTEM=="usb", ATTR{authorized}="0"',
        'boot/cmdline.txt': 'console=tty1 quiet',
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    config = tmp_path / 'kernel.config'
    config.write_text('\n'.join('# ' + option + ' is not set' for option in airgap.REQUIRED_DISABLED))
    return root, config


def test_static_release_policy_passes(tmp_path):
    root, config = image(tmp_path)
    assert airgap.inspect_image(root, config) == []


def test_missing_kernel_policy_and_root_shell_fail(tmp_path):
    root, config = image(tmp_path)
    config.write_text('CONFIG_WLAN=y\n')
    (root / 'etc/inittab').write_text('tty1::respawn:/bin/sh\n')
    failures = airgap.inspect_image(root, config)
    assert 'CONFIG_WLAN must be explicitly disabled' in failures
    assert 'automatic root shell/login in inittab' in failures


def test_external_symlink_fails_closed(tmp_path):
    root, config = image(tmp_path)
    (root / 'etc/shadow').unlink()
    (root / 'etc/shadow').symlink_to(config)
    assert 'external symlink: etc/shadow' in airgap.inspect_image(root, config)


def test_enabled_network_and_missing_firewall_fail(tmp_path):
    root, config = image(tmp_path)
    (root / 'etc/init.d').mkdir()
    (root / 'etc/init.d/network').write_text('/usr/sbin/wpa_supplicant\n')
    (root / 'etc/nftables.conf').unlink()
    failures = airgap.inspect_image(root, config)
    assert 'missing etc/nftables.conf' in failures
    assert 'network/debug service configuration: etc/init.d/network' in failures
