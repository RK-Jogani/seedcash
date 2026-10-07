"""Focused tests for current SeedCash APIs; synthetic data only."""
import json
from pathlib import Path
import pytest
from seedcash.helpers.ur2.cbor_lite import CBOREncoder
from seedcash.helpers.ur2.ur import UR
from seedcash.helpers.ur2.ur_encoder import UREncoder
from seedcash.models.decode_qr import DecodeQR
from seedcash.models.decode_qr import DecodeQRStatus
from seedcash.models.psbt_parser import PSBTParser
from seedcash.models.psbt_parser import parse_keypairs
from seedcash.models.psbt_parser import parse_psbt
from seedcash.models.psbt_signer import _serialize_keypairs
from seedcash.helpers.qr import QR
from seedcash.helpers.ur2.constants import MAX_SEQ_LEN
from seedcash.helpers.ur2.fountain_encoder import FountainEncoder
from seedcash.helpers.ur2.bytewords import Bytewords
from seedcash.helpers.ur2.bytewords import Bytewords_Style_minimal
from seedcash.helpers.ur2.cbor_lite import CBORDecoder
from seedcash.helpers.ur2.ur_decoder import URDecoder
from seedcash.helpers.ur2.ur_decoder import InvalidSequenceComponent
from seedcash.models.encode_qr import UrPsbtQrEncoder
psbt_receiver_DATA = json.loads(Path(__file__).with_name('psbtV145CashTokenScenarios.json').read_text())

def psbt_receiver_fixture():
    return bytes.fromhex(psbt_receiver_DATA['materializedFixtures'][0]['psbtHex'])

def psbt_receiver_with_version(value):
    raw = psbt_receiver_fixture()
    (pairs, end) = parse_keypairs(raw, 5)
    pairs = [(k, value if k == b'\xfb' else v) for (k, v) in pairs]
    return b'psbt\xff' + _serialize_keypairs(pairs) + b'\x00' + raw[end:]

def psbt_receiver_lab_ur(raw, max_fragment_len=65):
    wrapper = CBOREncoder()
    wrapper.encodeBytes(raw)
    return UREncoder(UR('crypto-psbt', wrapper.get_bytes()), max_fragment_len=max_fragment_len)

class TestPsbtReceiver:

    @staticmethod
    @pytest.mark.parametrize('item', psbt_receiver_DATA['materializedFixtures'], ids=lambda x: x.get('id', 'fixture'))
    def test_valid_lab_transfers_and_tokens_decode_and_parse(item):
        raw = bytes.fromhex(item['psbtHex'])
        encoder = psbt_receiver_lab_ur(raw)
        receiver = DecodeQR()
        for _ in range(4 * encoder.fountain_encoder.seq_len()):
            status = receiver.add_data(encoder.next_part())
            if status == DecodeQRStatus.COMPLETE:
                break
        assert status == DecodeQRStatus.COMPLETE
        assert receiver.get_psbt() == raw
        parsed = PSBTParser(receiver.get_psbt())
        assert parsed.parsed['psbt_version'] == 145
        assert parsed.parsed['unsigned_tx'].hex() == item['unsignedTransactionHex']

    @staticmethod
    @pytest.mark.parametrize('version', [b'', b'\x91', b'\x91\x00', b'\x91\x00\x00', b'\x91\x00\x00\x00\x00', b'\x00\x00\x00\x91', 2 .to_bytes(4, 'little'), 146 .to_bytes(4, 'little')])
    def test_bad_version_rejected(version):
        with pytest.raises(ValueError):
            parse_psbt(psbt_receiver_with_version(version))

    @staticmethod
    def test_version145_is_exact_uint32_little_endian():
        parsed = parse_psbt(psbt_receiver_with_version(b'\x91\x00\x00\x00'))
        assert parsed['psbt_version'] == 145

    @staticmethod
    def test_corrupted_ur_checksum_is_invalid_and_never_complete():
        receiver = DecodeQR()
        encoded = psbt_receiver_lab_ur(psbt_receiver_fixture()).next_part()
        damaged = encoded[:-2] + ('ae' if encoded[-2:] != 'ae' else 'ad')
        assert receiver.add_data(damaged) == DecodeQRStatus.INVALID
        assert receiver.is_invalid and (not receiver.is_complete) and (receiver.get_psbt() is None)
        assert receiver.decoder is None
        assert receiver.add_data(encoded) == DecodeQRStatus.INVALID

    @staticmethod
    def test_duplicate_fragment_is_harmless_but_mixed_message_is_rejected():
        receiver = DecodeQR()
        encoder = psbt_receiver_lab_ur(psbt_receiver_fixture())
        first = encoder.next_part()
        assert receiver.add_data(first) == DecodeQRStatus.PART_COMPLETE
        assert receiver.add_data(first) == DecodeQRStatus.PART_EXISTING
        other = psbt_receiver_lab_ur(psbt_receiver_fixture()[:-1])
        assert receiver.add_data(other.next_part()) == DecodeQRStatus.INVALID
        assert not receiver.is_complete and receiver.get_psbt() is None

    @staticmethod
    @pytest.mark.parametrize('data', [object(), 3, 'UR:CRYPTO-PSBT/' + 'a' * 16385])
    def test_bad_scan_types_and_sizes_do_not_raise(data):
        receiver = DecodeQR()
        assert receiver.add_data(data) == DecodeQRStatus.INVALID

    @staticmethod
    def test_every_truncated_psbt_prefix_fails_closed():
        raw = psbt_receiver_fixture()
        for length in range(len(raw)):
            with pytest.raises(ValueError):
                PSBTParser(raw[:length])

class TestQrSecurity:
    @staticmethod
    def test_qr_payload_is_passed_without_shell_interpretation(monkeypatch):
        payload = '$(echo synthetic); "quoted"'
        def capture(command, **kwargs):
            assert kwargs.get('shell', False) is False, 'QR payload reaches a shell'
            assert isinstance(command, list)
            assert payload in command
            raise RuntimeError('synthetic subprocess stop')
        monkeypatch.setattr('seedcash.helpers.qr.subprocess.call', capture)
        with pytest.raises(RuntimeError, match='synthetic subprocess stop'):
            QR().qrimage_io(payload)

    @staticmethod
    def test_qr_color_rejects_command_injection_before_execution(monkeypatch):
        def unexpected(*args, **kwargs):
            pytest.fail('Invalid QR color reached subprocess execution')
        monkeypatch.setattr('seedcash.helpers.qr.subprocess.call', unexpected)
        with pytest.raises(ValueError):
            QR().qrimage_io('synthetic', background_color='ffffff;echo injected')


def ur_security_regressions_fixture_psbt():
    fixture = json.loads(Path(__file__).with_name('psbtV145CashTokenScenarios.json').read_text())
    return bytes.fromhex(fixture['materializedFixtures'][0]['psbtHex'])

class TestUrSecurityRegressions:

    @staticmethod
    def test_sequence_component_rejects_excessive_seq_len():
        with pytest.raises(InvalidSequenceComponent):
            URDecoder.parse_sequence_component(f'1-{MAX_SEQ_LEN + 1}')

    @staticmethod
    def test_single_part_is_rejected_while_fountain_in_progress():
        message = b'x' * 200
        fountain = FountainEncoder(message, max_fragment_len=12)
        first_part = fountain.next_part()
        first_encoded = UREncoder.encode_part('crypto-psbt', first_part)
        decoder = URDecoder()
        assert decoder.receive_part(first_encoded) is True
        assert decoder.result is None
        attacker_single = UREncoder.encode(UR('crypto-psbt', b'attacker-message'))
        assert decoder.receive_part(attacker_single) is False
        assert decoder.result is None

    @staticmethod
    def test_crypto_psbt_encoder_uses_standard_cbor_bytestring():
        psbt = ur_security_regressions_fixture_psbt()
        encoder = UrPsbtQrEncoder(psbt=bytearray(psbt), qr_max_fragment_size=1024)
        part = encoder.next_part()
        (_, components) = URDecoder.parse(part)
        assert len(components) == 1
        wrapped_cbor = Bytewords.decode(Bytewords_Style_minimal, components[0])
        decoder = CBORDecoder(wrapped_cbor)
        (payload, _) = decoder.decodeBytes()
        assert payload == psbt
        decoded = URDecoder.decode_by_type('crypto-psbt', components[0])
        assert decoded.cbor == psbt

    @staticmethod
    def test_crypto_psbt_fountain_decode_unwraps_standard_cbor_bytestring():
        psbt = ur_security_regressions_fixture_psbt()
        encoder = UrPsbtQrEncoder(psbt=bytearray(psbt), qr_max_fragment_size=12)
        decoder = URDecoder()
        for _ in range(4 * encoder.seq_len()):
            assert decoder.receive_part(encoder.next_part()) is True
            if decoder.is_success():
                break
        assert decoder.is_success()
        assert decoder.result.cbor == psbt

    @staticmethod
    @pytest.mark.parametrize('style', [1, 2, 3])
    def test_bytewords_crc_roundtrip_and_corruption(style):
        from seedcash.helpers.ur2.bytewords import get_word, get_minimal_word
        from seedcash.helpers.ur2.crc32 import crc32n
        body = b'checksum protected body'
        assert Bytewords.decode(style, Bytewords.encode(style, body)) == body
        checksum = crc32n(body)
        separator = {1: ' ', 2: '-', 3: ''}[style]
        word = get_minimal_word if style == 3 else get_word
        for damaged in (bytes([body[0] ^ 1]) + body[1:] + checksum, body + checksum[:-1] + bytes([checksum[-1] ^ 1]), body + checksum[:-1], body + checksum + b'\x00'):
            encoded = separator.join((word(byte) for byte in damaged))
            with pytest.raises(ValueError):
                Bytewords.decode(style, encoded)

    @staticmethod
    @pytest.mark.parametrize('field', ['seq_len', 'message_len', 'checksum', 'data', 'type'])
    def test_mixed_fountain_identity_is_rejected(field):
        from seedcash.helpers.ur2.fountain_encoder import Part
        source = FountainEncoder(b'a' * 200, max_fragment_len=12)
        first = source.next_part()
        second = source.next_part()
        decoder = URDecoder()
        assert decoder.receive_part(UREncoder.encode_part('bytes', first))
        changed = Part(second.seq_num, second.seq_len, second.message_len, second.checksum, second.data)
        ur_type = 'bytes'
        if field == 'data':
            changed.data += b'\x00'
        elif field == 'type':
            ur_type = 'crypto-psbt'
        else:
            setattr(changed, field, getattr(changed, field) + 1)
        assert not decoder.receive_part(UREncoder.encode_part(ur_type, changed))
        assert decoder.result is None
        assert decoder.receive_part(UREncoder.encode_part('bytes', second))
        other = FountainEncoder(b'b' * 200, max_fragment_len=12)
        assert not decoder.receive_part(UREncoder.encode_part('bytes', other.next_part()))
        decoder = URDecoder()
        assert decoder.receive_part(UREncoder.encode_part('bytes', other.next_part()))

    @staticmethod
    def test_invalid_first_part_does_not_bind_type():
        decoder = URDecoder()
        assert not decoder.receive_part('ur:crypto-psbt/notbytewords')
        assert decoder.expected_type is None
        assert decoder.receive_part(UREncoder.encode(UR('bytes', b'valid')))


class TestChecksums:
    @staticmethod
    @pytest.mark.parametrize('payload', [b'', bytes.fromhex('00009070'), b'checksum protected body'])
    def test_crc_bytes_match_independent_standard_library(payload):
        import zlib
        from seedcash.helpers.ur2.crc32 import crc32n
        assert crc32n(payload) == zlib.crc32(payload).to_bytes(4, 'big')
