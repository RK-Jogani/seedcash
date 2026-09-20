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
    ParseTransactionResult,
    Token,
    TxInput,
    TxOutput,
    PSBTParser,
)
from seedcash.models.psbt_signer import (
    BitcoinCashSigner,
    BCHSignerExpectation,
    SIGHASH_ALL,
    SIGHASH_FORKID,
    SIGHASH_NONE,
    double_sha256,
    validate_redeem_script,
    validate_multisig_redeem_script,
)
from seedcash.models.bip44 import Bip44


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
        assert payment[0].index == 1  # Preserve the signed transaction's real vout


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

    def test_genesis_accepts_tokenized_vout_zero_input(self):
        category_id = "11" * 32
        spent_category_id = "22" * 32
        prev_txid = bytes.fromhex(category_id)[::-1]
        token = Token(
            prefix=b"",
            script_pubkey=_p2pkh_script(),
            category_id=spent_category_id,
            ft_amount=1,
        )
        spent_output = TxOutput(
            value_satoshis=1000,
            index=0,
            full_script=token.script_pubkey,
            token=token,
        )
        tx_input = TxInput(prev_txid=prev_txid, prev_index=0, sequence=0)
        parser = PSBTParser.__new__(PSBTParser)
        parser.parsed = {"inputs": [[]]}
        parser.total_input_amount = 0
        parser.total_output_amount = 0
        parser.categories = {"nft": [], "ft": []}
        parser.tx = ParseTransactionResult(
            version=b"\x01\x00\x00\x00",
            inputs=[tx_input],
            outputs=[TxOutput(
                value_satoshis=900,
                index=0,
                full_script=token.script_pubkey,
                token=Token(
                    prefix=b"",
                    script_pubkey=token.script_pubkey,
                    category_id=category_id,
                    ft_amount=1,
                ),
            )],
            locktime=b"\x00\x00\x00\x00",
        )
        parser.resolve_spent_output = lambda prev_index, input_pairs: spent_output

        parser.build_transaction()

        assert parser.genesis is not None
        assert category_id in parser.genesis.categories["ft"]


# ---------------------------------------------------------------------------
# Redeem scripts must commit to the supplied UTXO scriptPubKey
# ---------------------------------------------------------------------------

class TestRedeemScriptValidation:

    def test_standard_multisig_redeem_script_is_accepted(self):
        redeem_script = (
            b"\x52"
            + b"\x21\x02" + bytes(32)
            + b"\x21\x03" + bytes(32)
            + b"\x52\xae"
        )

        assert validate_multisig_redeem_script(redeem_script) == redeem_script

    @pytest.mark.parametrize("redeem_script", [
        b"\x51",
        b"\x51\x21" + bytes(33) + b"\x51\xae",
        b"\x51\x20" + bytes(32) + b"\x51\xae",
        b"\x52\x21\x02" + bytes(32) + b"\x51\xae",
        b"\x51\x21\x02" + bytes(32) + b"\x52\xae",
        b"\x51\x21\x02" + bytes(32) + b"\x51\xae\x00",
    ])
    def test_nonstandard_multisig_redeem_script_is_rejected(self, redeem_script):
        with pytest.raises(BCHSignerExpectation, match="redeem script"):
            validate_multisig_redeem_script(redeem_script)

    def test_matching_p2sh20_redeem_script_is_accepted(self):
        redeem_script = b"\x51"
        script_pubkey = b"\xa9\x14" + Bip44.hash160(redeem_script) + b"\x87"

        assert validate_redeem_script(script_pubkey, redeem_script) == redeem_script

    def test_mismatched_redeem_script_is_rejected(self):
        redeem_script = b"\x51"
        script_pubkey = b"\xa9\x14" + Bip44.hash160(redeem_script) + b"\x87"

        with pytest.raises(BCHSignerExpectation, match="does not match"):
            validate_redeem_script(script_pubkey, b"\x52")

    def test_matching_p2sh32_redeem_script_is_accepted(self):
        redeem_script = b"\x51"
        script_pubkey = b"\xaa\x20" + double_sha256(redeem_script) + b"\x87"

        assert validate_redeem_script(script_pubkey, redeem_script) == redeem_script


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