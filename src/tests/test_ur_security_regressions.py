import pytest

from seedcash.helpers.ur2.constants import MAX_SEQ_LEN
from seedcash.helpers.ur2.fountain_encoder import FountainEncoder
from seedcash.helpers.ur2.bytewords import Bytewords, Bytewords_Style_minimal
from seedcash.helpers.ur2.cbor_lite import CBORDecoder
from seedcash.helpers.ur2.ur import UR
from seedcash.helpers.ur2.ur_decoder import URDecoder, InvalidSequenceComponent
from seedcash.helpers.ur2.ur_encoder import UREncoder
from seedcash.models.encode_qr import UrPsbtQrEncoder
from tests.test_ur_export_policy import fixture_psbt


def test_sequence_component_rejects_excessive_seq_len():
    with pytest.raises(InvalidSequenceComponent):
        URDecoder.parse_sequence_component(f"1-{MAX_SEQ_LEN + 1}")


def test_single_part_is_rejected_while_fountain_in_progress():
    message = b"x" * 200
    fountain = FountainEncoder(message, max_fragment_len=12)
    first_part = fountain.next_part()
    first_encoded = UREncoder.encode_part("crypto-psbt", first_part)

    decoder = URDecoder()
    assert decoder.receive_part(first_encoded) is True
    assert decoder.result is None

    attacker_single = UREncoder.encode(UR("crypto-psbt", b"attacker-message"))
    assert decoder.receive_part(attacker_single) is False
    assert decoder.result is None


def test_crypto_psbt_encoder_uses_standard_cbor_bytestring():
    psbt = fixture_psbt()
    encoder = UrPsbtQrEncoder(psbt=bytearray(psbt), qr_max_fragment_size=1024)
    part = encoder.next_part()

    _, components = URDecoder.parse(part)
    assert len(components) == 1

    wrapped_cbor = Bytewords.decode(Bytewords_Style_minimal, components[0])
    decoder = CBORDecoder(wrapped_cbor)
    payload, _ = decoder.decodeBytes()
    assert payload == psbt

    decoded = URDecoder.decode_by_type("crypto-psbt", components[0])
    assert decoded.cbor == psbt


def test_crypto_psbt_fountain_decode_unwraps_standard_cbor_bytestring():
    psbt = fixture_psbt()
    encoder = UrPsbtQrEncoder(psbt=bytearray(psbt), qr_max_fragment_size=12)
    decoder = URDecoder()

    while not decoder.is_success():
        assert decoder.receive_part(encoder.next_part()) is True

    assert decoder.result.cbor == psbt


@pytest.mark.parametrize('style', [1, 2, 3])
def test_bytewords_crc_roundtrip_and_corruption(style):
    from seedcash.helpers.ur2.bytewords import get_word, get_minimal_word
    from seedcash.helpers.ur2.crc32 import crc32n
    body = b'checksum protected body'
    assert Bytewords.decode(style, Bytewords.encode(style, body)) == body
    checksum = crc32n(body)
    separator = {1: ' ', 2: '-', 3: ''}[style]
    word = get_minimal_word if style == 3 else get_word
    for damaged in (bytes([body[0] ^ 1]) + body[1:] + checksum,
                    body + checksum[:-1] + bytes([checksum[-1] ^ 1]),
                    body + checksum[:-1], body + checksum + b'\x00'):
        encoded = separator.join(word(byte) for byte in damaged)
        with pytest.raises(ValueError):
            Bytewords.decode(style, encoded)


def test_crc_includes_leading_zero_bytes():
    from seedcash.helpers.ur2.crc32 import crc32n
    assert crc32n(bytes.fromhex('00009070')) == bytes.fromhex('0000243a')
    assert crc32n(b'') == b'\x00' * 4


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
    decoder.restart()
    assert decoder.receive_part(UREncoder.encode_part('bytes', other.next_part()))


def test_invalid_first_part_does_not_bind_type():
    decoder = URDecoder()
    assert not decoder.receive_part('ur:crypto-psbt/notbytewords')
    assert decoder.expected_type is None
    assert decoder.receive_part(UREncoder.encode(UR('bytes', b'valid')))


def test_crypto_psbt_rejects_bad_cbor_and_trailing_bytes():
    from seedcash.helpers.ur2.cbor_lite import CBOREncoder
    for cbor in (b'not cbor', b'\x41x\x00'):
        decoder = URDecoder()
        assert not decoder.receive_part(UREncoder.encode(UR('crypto-psbt', cbor)))
        assert decoder.result is None
