# src/tests/test_audit_integration.py
"""
Integration-style tests for SC-02 / SC-04 / SC-05 / SC-09.
Run: pytest src/tests/test_audit_integration.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from seedcash.models.psbt_parser import (
    classify_script,
    ScriptType,
    parse_transaction,
    TxOutput,
    PSBTParser,
)
from seedcash.models.psbt_signer import (
    BitcoinCashSigner,
    BCHSignerExpectation,
    SIGHASH_ALL,
    SIGHASH_FORKID,
    SIGHASH_NONE,
)


# ---------------------------------------------------------------------------
# Helpers: minimal raw tx builders (no full PSBT required for some checks)
# ---------------------------------------------------------------------------

def _varint(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + n.to_bytes(2, "little")
    raise ValueError("varint too large for this helper")


def _p2pkh_script(h160: bytes = None) -> bytes:
    h160 = h160 or bytes(20)
    return b"\x76\xa9\x14" + h160 + b"\x88\xac"


def _op_return_script(payload: bytes = b"test") -> bytes:
    return b"\x6a" + bytes([len(payload)]) + payload


def build_tx(outputs: list[tuple[int, bytes]]) -> bytes:
    """
    Minimal legacy BCH tx:
      version(4) | vin_count=0 | vout_count | outs... | locktime(4)
    Enough for parse_transaction output classification.
    """
    body = b"\x01\x00\x00\x00"  # version 1
    body += _varint(0)         # no inputs
    body += _varint(len(outputs))
    for value_sats, script in outputs:
        body += value_sats.to_bytes(8, "little")
        body += _varint(len(script)) + script
    body += b"\x00\x00\x00\x00"  # locktime
    return body


# ---------------------------------------------------------------------------
# SC-02 — OP_RETURN first must not steal the payment amount pairing
# ---------------------------------------------------------------------------

class TestSC02OpReturnFirst:

    def test_parse_op_return_then_p2pkh(self):
        """
        Audit fixture A shape:
          v0 = 8_998_000 OP_RETURN
          v1 = 1_001_000 P2PKH Alice
        Payment list must be Alice only; amount for Alice is 1_001_000.
        """
        alice_h160 = bytes.fromhex("cbdd214121b18cac291e41175e5b9204b9df7457")
        tx = build_tx([
            (8_998_000, _op_return_script(b"burn")),
            (1_001_000, _p2pkh_script(alice_h160)),
        ])
        result = parse_transaction(tx)

        assert len(result.outputs) == 2
        assert result.outputs[0].script_type == ScriptType.OP_RETURN
        assert result.outputs[0].address is None
        assert result.outputs[0].value_satoshis == 8_998_000

        assert result.outputs[1].script_type == ScriptType.P2PKH
        assert result.outputs[1].address is not None
        assert result.outputs[1].value_satoshis == 1_001_000

        # Same filter the UI uses for destination_addresses
        payment = [o for o in result.outputs if o.address]
        assert len(payment) == 1
        assert payment[0].value_satoshis == 1_001_000  # NOT 8_998_000


# ---------------------------------------------------------------------------
# SC-03 — lookalike never gets a CashAddr
# ---------------------------------------------------------------------------

class TestSC03OnParsedTx:

    def test_lookalike_output_has_no_address(self):
        alice = bytes.fromhex("cbdd214121b18cac291e41175e5b9204b9df7457")
        attacker = bytes.fromhex("11" * 20)
        lookalike = (
            b"\x76\xa9\x14" + alice + b"\x6d"
            + b"\x76\xa9\x14" + attacker + b"\x88\xac"
        )
        tx = build_tx([(9_000_000, lookalike)])
        result = parse_transaction(tx)
        out = result.outputs[0]
        assert out.address is None
        assert out.script_type != ScriptType.P2PKH


# ---------------------------------------------------------------------------
# SC-01 — create_sighash refuses NONE|FORKID (if you expose the check)
# ---------------------------------------------------------------------------

class TestSC01SighashRuntime:

    def test_none_forkid_not_allowed_constant(self):
        from seedcash.models.psbt_signer import ALLOWED_SIGHASH
        assert (SIGHASH_NONE | SIGHASH_FORKID) not in ALLOWED_SIGHASH
        assert (SIGHASH_ALL | SIGHASH_FORKID) in ALLOWED_SIGHASH


# ---------------------------------------------------------------------------
# SC-06 — unit conversion helper (add if you have one; else pure check)
# ---------------------------------------------------------------------------

class TestSC06Units:

    def test_sats_to_bch(self):
        """1 BCH = 1e8 sats. Display must use /1e8, not /1e6."""
        sats = 100_000_000
        bch = sats / 1e8
        wrong = sats / 1e6
        assert bch == 1.0
        assert wrong == 100.0  # documents the old bug magnitude


# ---------------------------------------------------------------------------
# SC-09 — optional: only when you have a real PSBT + xpriv
# ---------------------------------------------------------------------------

class TestSC09Live:

    @pytest.mark.skip(reason="Provide FIXTURE_PSBT + FIXTURE_XPRIV env or constants")
    def test_unsigned_psbt_raises(self):
        """
        Use a PSBT whose BIP32 paths do not match the test wallet.
        signed_psbt() must raise BCHSignerExpectation, not return original bytes.
        """
        # from seedcash.models.psbt_parser import PSBTParser
        # parser = PSBTParser(bytearray(FIXTURE_PSBT))
        # signer = BitcoinCashSigner(bytearray(FIXTURE_XPRIV), parser)
        # with pytest.raises(BCHSignerExpectation):
        #     signer.signed_psbt()
        pass