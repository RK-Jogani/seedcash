import json
from pathlib import Path

import pytest
from seedcash.helpers.ur2.bytewords import Bytewords, Bytewords_Style_minimal
from seedcash.helpers.ur2.ur_decoder import URDecoder
from seedcash.models.encode_qr import UrPsbtQrEncoder
from seedcash.models.psbt_export import validate_psbt_export
from seedcash.models.psbt_parser import parse_keypairs
from seedcash.models.psbt_signer import _serialize_keypairs


def fixture_psbt():
    fixture = json.loads(Path(__file__).with_name('psbtV145CashTokenScenarios.json').read_text())
    return bytes.fromhex(fixture['materializedFixtures'][0]['psbtHex'])


@pytest.mark.parametrize('secret', [b'mnemonic', b'seed', b'private_key', b'passphrase', b'master_secret', b'xprv', bytes(range(32))])
def test_proprietary_secret_cannot_be_exported(secret):
    original = fixture_psbt()
    pairs, end = parse_keypairs(original, 5)
    injected = b'psbt\xff' + _serialize_keypairs(pairs + [(b'\xfcwallet-secret', secret)]) + b'\x00' + original[end:]
    with pytest.raises(ValueError, match='disallowed'):
        UrPsbtQrEncoder(psbt=bytearray(injected))


def test_export_is_independent_of_unrelated_wallet_secrets():
    psbt = fixture_psbt()
    exported = []
    for secret in (b'first wallet seed and passphrase', b'other private_key xprv master_secret'):
        encoder = UrPsbtQrEncoder(psbt=bytearray(psbt))
        # Unrelated state is never an input to the serializer.
        encoder.unrelated_wallet_state = {'mnemonic': secret, 'seed': secret}
        decoder = URDecoder()
        for _ in range(encoder.seq_len()):
            assert decoder.receive_part(encoder.next_part())
        result = decoder.result_message().cbor
        assert secret not in result
        assert result == psbt
        assert encoder.psbt is None
        exported.append(result)
    assert exported[0] == exported[1]


def test_export_rejects_non_psbt_bytes():
    with pytest.raises(ValueError):
        validate_psbt_export(b'raw seed material')
