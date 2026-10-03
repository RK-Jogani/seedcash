from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from seedcash.helpers.qr import QR


@pytest.mark.parametrize('outcome', ['success', 'command_failure', 'image_failure', 'exception'])
def test_qr_subprocess_has_no_shell_and_cleans_temporary_files(monkeypatch, outcome):
    paths = []
    payload = '$(touch /tmp/never-execute); "quoted"'

    def run(command, **kwargs):
        assert isinstance(command, list)
        assert command[-2:] == ['--', payload]
        assert kwargs.get('shell', False) is False
        path = Path(command[command.index('-o') + 1])
        paths.append(path)
        assert path.parent.stat().st_mode & 0o077 == 0
        if outcome == 'exception':
            path.write_bytes(b'partial')
            raise RuntimeError('test failure')
        if outcome == 'image_failure':
            path.write_bytes(b'invalid image')
        else:
            Image.new('RGB', (10, 10)).save(path)
        return SimpleNamespace(returncode=1 if outcome == 'command_failure' else 0)

    monkeypatch.setattr('seedcash.helpers.qr.subprocess.run', run)
    if outcome in ('exception', 'image_failure'):
        with pytest.raises(Exception):
            QR().qrimage_io(payload)
    else:
        image = QR().qrimage_io(payload)
        assert image.size == (240, 240)
        assert image.getpixel((0, 0)) is not None
    assert paths
    assert not paths[0].exists()
    assert not paths[0].parent.exists()


@pytest.mark.parametrize('kwargs', [
    {'border': True}, {'border': 0}, {'background_color': 'ffffff;echo'},
    {'width': 100000}, {'data': 'x' * 4097}, {'data': '\x00'},
])
def test_invalid_qr_arguments_are_rejected_before_subprocess(monkeypatch, kwargs):
    monkeypatch.setattr('seedcash.helpers.qr.subprocess.run', lambda *a, **kw: pytest.fail('subprocess called'))
    arguments = {'data': 'safe'}
    arguments.update(kwargs)
    with pytest.raises(ValueError):
        QR().qrimage_io(**arguments)
