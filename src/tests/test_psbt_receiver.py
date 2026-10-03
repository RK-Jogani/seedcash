"""Receiver contract: uint32 version, transport integrity and safe scan rejection."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from seedcash.helpers.ur2.cbor_lite import CBOREncoder
from seedcash.helpers.ur2.ur import UR
from seedcash.helpers.ur2.ur_encoder import UREncoder
from seedcash.models.decode_qr import DecodeQR, DecodeQRStatus
from seedcash.models.psbt_parser import PSBTParser, parse_keypairs, parse_psbt
from seedcash.models.psbt_signer import _serialize_keypairs
from seedcash.views import psbt_views as views
from seedcash.views.scan_view import ScanPSBTView

DATA = json.loads(Path(__file__).with_name('psbtV145CashTokenScenarios.json').read_text())


def fixture():
    return bytes.fromhex(DATA['materializedFixtures'][0]['psbtHex'])


def with_version(value):
    raw = fixture()
    pairs, end = parse_keypairs(raw, 5)
    pairs = [(k, value if k == b'\xfb' else v) for k, v in pairs]
    return b'psbt\xff' + _serialize_keypairs(pairs) + b'\0' + raw[end:]


def lab_ur(raw, max_fragment_len=65):
    # Generator deliberately accepts arbitrary bytes to produce malformed scans.
    wrapper = CBOREncoder()
    wrapper.encodeBytes(raw)
    return UREncoder(UR('crypto-psbt', wrapper.get_bytes()), max_fragment_len=max_fragment_len)


@pytest.mark.parametrize('item', DATA['materializedFixtures'], ids=lambda x: x.get('id','fixture'))
def test_valid_lab_transfers_and_tokens_decode_and_parse(item):
    raw = bytes.fromhex(item['psbtHex'])
    encoder = lab_ur(raw)
    receiver = DecodeQR()
    for _ in range(encoder.fountain_encoder.seq_len()):
        status = receiver.add_data(encoder.next_part())
    assert status == DecodeQRStatus.COMPLETE
    assert receiver.get_psbt() == raw
    parsed = PSBTParser(receiver.get_psbt())
    assert parsed.parsed['psbt_version'] == 145
    assert parsed.parsed['unsigned_tx'].hex() == item['unsignedTransactionHex']


@pytest.mark.parametrize('version', [b'', b'\x91', b'\x91\0', b'\x91\0\0', b'\x91\0\0\0\0',
                                     b'\0\0\0\x91', (2).to_bytes(4,'little'), (146).to_bytes(4,'little')])
def test_bad_version_rejected(version):
    with pytest.raises(ValueError):
        parse_psbt(with_version(version))


def test_version145_is_exact_uint32_little_endian():
    parsed = parse_psbt(with_version(b'\x91\0\0\0'))
    assert parsed['psbt_version'] == 145


@pytest.mark.parametrize('raw', [fixture()[:-1], with_version(b'\x91'), with_version((999).to_bytes(4,'little'))], ids=['truncated','short-version','unsupported-version'])
def test_bad_payload_reaches_controlled_screen_and_clears_scan(monkeypatch, raw):
    encoder, receiver = lab_ur(raw), DecodeQR()
    for _ in range(encoder.fountain_encoder.seq_len()):
        receiver.add_data(encoder.next_part())
    assert receiver.is_complete  # Transport success is separate from PSBT validity.
    ctl = SimpleNamespace(psbt_bytes=bytearray(receiver.get_psbt()), psbt_parser=object(),
                          token_review=object(), token_review_parser=object(), token_review_acknowledged={0})
    def discard():
        if isinstance(ctl.psbt_bytes, bytearray):
            ctl.psbt_bytes[:] = b'\0' * len(ctl.psbt_bytes)
        ctl.psbt_bytes = b''
        ctl.psbt_parser = ctl.token_review = ctl.token_review_parser = None
        ctl.token_review_acknowledged = set()
    ctl.discard_psbt = Mock(side_effect=discard)
    monkeypatch.setattr(views.View, '__init__', lambda self: setattr(self, 'controller', ctl))
    monkeypatch.setattr('seedcash.gui.screens.screen.LoadingScreenThread', Mock())
    monkeypatch.setattr(views.time, 'sleep', lambda _: None)
    destination = views.LoadingPSBTView().run()
    assert destination.View_cls is views.PSBTInvalidTransactionView
    assert destination.clear_history
    assert ctl.psbt_parser is None and ctl.psbt_bytes == b''
    assert ctl.token_review is None and not ctl.token_review_acknowledged
    invalid = views.PSBTInvalidTransactionView.__new__(views.PSBTInvalidTransactionView)
    invalid.controller, invalid.run_screen = ctl, Mock(return_value=0)
    invalid.run()
    assert invalid.run_screen.call_args.kwargs['title'] == 'Invalid or unsupported PSBT'
    assert ctl.psbt_parser is None and ctl.psbt_bytes == b''
    confirmation = views.PSBTConfirmationView.__new__(views.PSBTConfirmationView)
    confirmation.controller = ctl
    assert confirmation.run().View_cls is views.MainMenuView


def test_corrupted_ur_checksum_is_invalid_and_never_complete():
    receiver = DecodeQR()
    encoded = lab_ur(fixture()).next_part()
    damaged = encoded[:-2] + ('ae' if encoded[-2:] != 'ae' else 'ad')
    assert receiver.add_data(damaged) == DecodeQRStatus.INVALID
    assert receiver.is_invalid and not receiver.is_complete and receiver.get_psbt() is None
    assert receiver.decoder is None
    assert receiver.add_data(encoded) == DecodeQRStatus.INVALID
    ctl = SimpleNamespace(discard_psbt=Mock(), reset_screensaver_timeout=Mock())
    scan = ScanPSBTView.__new__(ScanPSBTView)
    scan.controller, scan.decoder, scan.run_screen = ctl, receiver, Mock(return_value=True)
    assert scan.run().View_cls is views.PSBTInvalidTransactionView
    ctl.discard_psbt.assert_called_once()


def test_duplicate_fragment_is_harmless_but_mixed_message_is_rejected():
    receiver = DecodeQR()
    encoder = lab_ur(fixture())
    first = encoder.next_part()
    assert receiver.add_data(first) == DecodeQRStatus.PART_COMPLETE
    assert receiver.add_data(first) == DecodeQRStatus.PART_EXISTING
    other = lab_ur(fixture()[:-1])
    assert receiver.add_data(other.next_part()) == DecodeQRStatus.INVALID
    assert not receiver.is_complete and receiver.get_psbt() is None


@pytest.mark.parametrize('data', [object(), 3, 'UR:CRYPTO-PSBT/'+'a'*16385])
def test_bad_scan_types_and_sizes_do_not_raise(data):
    receiver = DecodeQR()
    assert receiver.add_data(data) == DecodeQRStatus.INVALID


@pytest.mark.parametrize('vector', DATA['materializedNegativeVectors'], ids=lambda x: x.get('id','negative'))
def test_lab_mismatched_transaction_vectors_rejected(vector):
    with pytest.raises(ValueError):
        PSBTParser(bytes.fromhex(vector['psbtHex']))


def test_every_truncated_psbt_prefix_fails_closed():
    raw = fixture()
    for length in range(len(raw)):
        with pytest.raises(ValueError):
            PSBTParser(raw[:length])
