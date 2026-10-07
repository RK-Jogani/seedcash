"""Focused tests for current SeedCash APIs; synthetic data only."""
import json
from types import SimpleNamespace
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


def psbt_receiver_lab_ur(raw, max_fragment_len=65):
    wrapper = CBOREncoder()
    wrapper.encodeBytes(raw)
    return UREncoder(UR('crypto-psbt', wrapper.get_bytes()), max_fragment_len=max_fragment_len)

class TestPsbtReceiver:

    @staticmethod
    @pytest.mark.parametrize('paytaca_separator', [False, True], ids=['ordinary-maps', 'paytaca-maps'])
    @pytest.mark.parametrize('item', psbt_receiver_DATA['materializedFixtures'], ids=lambda x: x.get('id', 'fixture'))
    def test_valid_lab_transfers_and_tokens_decode_and_parse(item, paytaca_separator):
        raw = bytes.fromhex(item['psbtHex'])
        if paytaca_separator:
            boundary = parse_psbt(raw)['input_ends']
            raw = raw[:boundary] + b'\x00' + raw[boundary:]
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
            assert kwargs['input'] == payload.encode()
            assert payload not in command
            assert kwargs['timeout'] == 5
            raise RuntimeError('synthetic subprocess stop')
        monkeypatch.setattr('seedcash.helpers.qr.subprocess.run', capture)
        with pytest.raises(RuntimeError, match='synthetic subprocess stop'):
            QR().qrimage_io(payload)

    @staticmethod
    def test_qr_color_rejects_command_injection_before_execution(monkeypatch):
        def unexpected(*args, **kwargs):
            pytest.fail('Invalid QR color reached subprocess execution')
        monkeypatch.setattr('seedcash.helpers.qr.subprocess.run', unexpected)
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


class TestQrProcessBoundary:
    @staticmethod
    @pytest.mark.parametrize('outcome', ['success', 'failure', 'missing', 'timeout', 'bad-image'])
    def test_temporary_output_is_private_and_removed(monkeypatch, outcome):
        import subprocess
        from PIL import Image
        paths = []
        def encode(command, **kwargs):
            assert isinstance(command, list)
            assert not kwargs.get('shell', False)
            assert kwargs['input'] == b'synthetic payload'
            output = Path(command[command.index('-o') + 1])
            paths.append(output)
            assert output.parent.stat().st_mode & 0o077 == 0
            if outcome == 'missing':
                raise FileNotFoundError('qrencode unavailable')
            if outcome == 'timeout':
                raise subprocess.TimeoutExpired(command, 5)
            if outcome == 'bad-image':
                output.write_bytes(b'not a PNG')
            else:
                Image.new('RGB', (20, 20)).save(output)
            return SimpleNamespace(returncode=1 if outcome == 'failure' else 0)
        monkeypatch.setattr('seedcash.helpers.qr.subprocess.run', encode)
        image = QR().qrimage_io('synthetic payload')
        assert image.size == (240, 240)
        assert image.mode == 'RGBA'
        assert paths and not paths[0].parent.exists()

    @staticmethod
    @pytest.mark.parametrize('options', [
        {'width': True}, {'width': 0}, {'height': 2049}, {'border': True},
        {'border': -1}, {'background_color': 'white;echo'}, {'data': object()},
        {'data': b'x' * 4097}, {'data': ''},
    ])
    def test_invalid_options_never_start_encoder(monkeypatch, options):
        def unexpected(*args, **kwargs):
            pytest.fail('Invalid arguments reached external encoder')
        monkeypatch.setattr('seedcash.helpers.qr.subprocess.run', unexpected)
        kwargs = {'data': 'synthetic'}
        kwargs.update(options)
        with pytest.raises(ValueError):
            QR().qrimage_io(**kwargs)


class TestUrBoundaries:
    @staticmethod
    @pytest.mark.parametrize('cbor', [b'not cbor', b'Ax\x00', b'\x40'])
    def test_crypto_psbt_requires_one_nonempty_cbor_bytestring(cbor):
        receiver = DecodeQR()
        assert receiver.add_data(UREncoder.encode(UR('crypto-psbt', cbor))) == DecodeQRStatus.INVALID
        assert receiver.decoder is None
        assert not receiver.is_complete
        assert receiver.get_psbt() is None

    @staticmethod
    def test_rejected_scan_is_terminal_until_new_receiver():
        raw = psbt_receiver_fixture()
        valid = psbt_receiver_lab_ur(raw, max_fragment_len=4096).next_part()
        receiver = DecodeQR()
        assert receiver.add_data('ur:crypto-psbt/invalid') == DecodeQRStatus.INVALID
        assert receiver.add_data(valid) == DecodeQRStatus.INVALID
        fresh = DecodeQR()
        assert fresh.add_data(valid) == DecodeQRStatus.COMPLETE
        assert fresh.get_psbt() == raw

    @staticmethod
    @pytest.mark.parametrize('changes', [
        {'seq_num': 0}, {'seq_len': 0}, {'seq_len': 10001},
        {'message_len': 0}, {'message_len': 2097153}, {'checksum': 4294967296},
        {'data': b''}, {'seq_len': 2, 'message_len': 100},
    ])
    def test_invalid_header_does_not_bind_decoder(changes):
        from seedcash.helpers.ur2.fountain_encoder import Part
        values = {'seq_num': 1, 'seq_len': 1, 'message_len': 3, 'checksum': 0, 'data': b'abc'}
        values.update(changes)
        decoder = URDecoder()
        assert not decoder.receive_part(UREncoder.encode_part('bytes', Part(**values)))
        assert decoder.expected_type is None
        assert decoder.fountain_decoder.expected_part_indexes is None

    @staticmethod
    def test_trailing_fountain_cbor_is_rejected():
        encoder = FountainEncoder(b'x' * 100, max_fragment_len=12)
        part = encoder.next_part()
        body = Bytewords.encode(Bytewords_Style_minimal, part.cbor() + b'\x00')
        decoder = URDecoder()
        assert not decoder.receive_part(f'ur:bytes/{part.seq_num}-{part.seq_len}/{body}')
        assert decoder.expected_type is None
