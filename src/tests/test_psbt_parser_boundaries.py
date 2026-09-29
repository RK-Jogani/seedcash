import pytest

from seedcash.models.psbt_parser import parse_keypairs, parse_psbt, parse_transaction, read_varint


def test_non_minimal_compact_size_is_rejected():
    with pytest.raises(ValueError, match="non-minimal"):
        read_varint(b"\xfd\x01\x00", 0)


def test_truncated_compact_size_is_rejected():
    with pytest.raises(ValueError, match="truncated"):
        read_varint(b"\xfe\x01\x00", 0)


def test_duplicate_key_in_map_is_rejected():
    encoded = b"\x01\x01\x00" + b"\x01\x01\x00" + b"\x00"

    with pytest.raises(ValueError, match="duplicate"):
        parse_keypairs(encoded, 0)


def test_trailing_transaction_bytes_are_rejected():
    transaction = (
        b"\x01\x00\x00\x00"
        + b"\x00"
        + b"\x00"
        + b"\x00\x00\x00\x00"
        + b"\x00"
    )

    with pytest.raises(ValueError, match="trailing"):
        parse_transaction(transaction + b"\x00")


def test_unknown_global_field_is_rejected():
    psbt = b"psbt\xff" + b"\x01\x7f\x00" + b"\x00"

    with pytest.raises(ValueError, match="unknown PSBT global field"):
        parse_psbt(psbt)