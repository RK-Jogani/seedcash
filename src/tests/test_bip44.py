from base58 import b58decode, b58encode

from seedcash.models.bip44 import Bip44


def test_xpub_decode_rejects_invalid_checksum():
    xpub = Bip44.xpub_encode(
        b"\x00",
        b"\x00" * 4,
        b"\x00" * 4,
        b"\x11" * 32,
        b"\x02" + b"\x22" * 32,
    )
    raw_xpub = bytearray(b58decode(xpub))
    raw_xpub[20] ^= 1

    try:
        Bip44.xpub_decode(b58encode(raw_xpub))
    except ValueError as error:
        assert str(error) == "invalid xpub checksum"
    else:
        raise AssertionError("corrupted xpub was accepted")