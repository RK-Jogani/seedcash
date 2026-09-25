import pytest

from seedcash.helpers.ur2.constants import MAX_SEQ_LEN
from seedcash.helpers.ur2.fountain_encoder import FountainEncoder
from seedcash.helpers.ur2.bytewords import Bytewords, Bytewords_Style_minimal
from seedcash.helpers.ur2.cbor_lite import CBORDecoder
from seedcash.helpers.ur2.ur import UR
from seedcash.helpers.ur2.ur_decoder import URDecoder, InvalidSequenceComponent
from seedcash.helpers.ur2.ur_encoder import UREncoder
from seedcash.models.encode_qr import UrPsbtQrEncoder


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
    psbt = b"\x00\x01\x02\x03\x04"
    encoder = UrPsbtQrEncoder(psbt=bytearray(psbt))
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
    psbt = b"x" * 200
    encoder = UrPsbtQrEncoder(psbt=bytearray(psbt), qr_max_fragment_size=12)
    decoder = URDecoder()

    while not decoder.is_success():
        assert decoder.receive_part(encoder.next_part()) is True

    assert decoder.result.cbor == psbt
