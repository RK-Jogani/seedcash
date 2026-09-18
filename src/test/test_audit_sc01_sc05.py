# tests/test_audit_sc01_sc05.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from seedcash.models.psbt_signer import (
    ALLOWED_SIGHASH,
    SIGHASH_ALL,
    SIGHASH_NONE,
    SIGHASH_FORKID,
    SIGHASH_ANYONECANPAY,
    SIGHASH_UTXOS,
)
from seedcash.models.psbt_parser import (
    classify_script,
    ScriptType,
    parse_token_script,
)


# ---------------------------------------------------------------------------
# SC-01 — SIGHASH allowlist
# ---------------------------------------------------------------------------

class TestSC01Sighash:

    def test_allowed_all_forkid(self):
        assert (SIGHASH_ALL | SIGHASH_FORKID) in ALLOWED_SIGHASH

    def test_allowed_all_forkid_utxos(self):
        assert (SIGHASH_ALL | SIGHASH_FORKID | SIGHASH_UTXOS) in ALLOWED_SIGHASH

    def test_reject_none_forkid(self):
        """0x42 — post-sign output swap was exploitable."""
        bad = SIGHASH_NONE | SIGHASH_FORKID
        assert bad not in ALLOWED_SIGHASH

    def test_reject_none_acp_forkid(self):
        """0xC2 — same class of unbound outputs."""
        bad = SIGHASH_NONE | SIGHASH_ANYONECANPAY | SIGHASH_FORKID
        assert bad not in ALLOWED_SIGHASH

    def test_reject_without_forkid(self):
        assert SIGHASH_ALL not in ALLOWED_SIGHASH
        assert SIGHASH_NONE not in ALLOWED_SIGHASH


# ---------------------------------------------------------------------------
# SC-03 — P2PKH lookalike must NOT get an address
# ---------------------------------------------------------------------------

class TestSC03Lookalike:

    def test_standard_p2pkh_ok(self):
        # OP_DUP OP_HASH160 <20> OP_EQUALVERIFY OP_CHECKSIG  (25 bytes)
        h160 = bytes.fromhex("cbdd214121b18cac291e41175e5b9204b9df7457")
        script = b"\x76\xa9\x14" + h160 + b"\x88\xac"
        assert len(script) == 25
        stype, addr = classify_script(script)
        assert stype == ScriptType.P2PKH
        assert addr is not None
        assert addr.startswith("bitcoincash:q")

    def test_long_lookalike_rejected(self):
        """startswith/endswith only would accept this; len must be 25."""
        h160 = bytes.fromhex("cbdd214121b18cac291e41175e5b9204b9df7457")
        script = b"\x76\xa9\x14" + h160 + b"\x88\xac" + b"\x00" * 10
        assert len(script) != 25
        stype, addr = classify_script(script)
        assert stype != ScriptType.P2PKH
        assert addr is None

    def test_op2drop_lookalike_rejected(self):
        """
        Audit construction (~49 bytes):
        DUP HASH160 PUSH20(alice) OP_2DROP
        DUP HASH160 PUSH20(attacker) EQUALVERIFY CHECKSIG
        Must NOT display as Alice P2PKH.
        """
        alice = bytes.fromhex("cbdd214121b18cac291e41175e5b9204b9df7457")
        attacker = bytes.fromhex("11" * 20)
        script = (
            b"\x76\xa9\x14" + alice + b"\x6d"  # OP_2DROP
            + b"\x76\xa9\x14" + attacker + b"\x88\xac"
        )
        assert len(script) != 25
        stype, addr = classify_script(script)
        assert stype != ScriptType.P2PKH
        assert addr is None

    def test_p2pk_compressed(self):
        # 0x21 + 33-byte compressed pubkey + OP_CHECKSIG → 35 bytes
        script = b"\x21" + b"\x02" + (b"\x11" * 32) + b"\xac"
        assert len(script) == 35
        stype, addr = classify_script(script)
        assert stype == ScriptType.P2PK
        assert addr is None

    def test_p2pk_uncompressed(self):
        # 0x41 + 65-byte uncompressed pubkey + OP_CHECKSIG → 67 bytes
        script = b"\x41" + b"\x04" + (b"\x11" * 64) + b"\xac"
        assert len(script) == 67
        stype, addr = classify_script(script)
        assert stype == ScriptType.P2PK
        assert addr is None

    def test_op_return_no_address(self):
        script = b"\x6a\x04test"
        stype, addr = classify_script(script)
        assert stype == ScriptType.OP_RETURN
        assert addr is None


# ---------------------------------------------------------------------------
# SC-02 — payment list must not include non-address outputs
# ---------------------------------------------------------------------------

class TestSC02Pairing:

    def test_bch_outputs_only_have_address(self):
        scripts = [
            b"\x6a\x04dead",  # OP_RETURN → no address
            b"\x76\xa9\x14" + bytes(20) + b"\x88\xac",  # P2PKH
        ]
        addrs = []
        for s in scripts:
            stype, addr = classify_script(s)
            if addr:
                addrs.append(addr)
        assert len(addrs) == 1  # OP_RETURN filtered out

    def test_op_return_and_p2pk_filtered(self):
        items = [
            (ScriptType.OP_RETURN, None),
            (ScriptType.P2PK, None),
            (ScriptType.P2PKH, "bitcoincash:q..."),
        ]
        payment = [addr for st, addr in items if addr]
        assert len(payment) == 1


# ---------------------------------------------------------------------------
# SC-04 / SC-05 — token helpers (parser-level)
# ---------------------------------------------------------------------------

class TestSC04SC05Tokens:

    def test_token_prefix_rejected_reserved_bit(self):
        # bit 0x80 set → must reject
        script = b"\xef" + bytes(32) + b"\x80"
        assert parse_token_script(script) is None

    def test_plain_script_not_token(self):
        assert parse_token_script(b"\x76\xa9\x14" + bytes(20) + b"\x88\xac") is None


# ---------------------------------------------------------------------------
# SC-09 — no inputs to sign must raise (not return original PSBT)
# ---------------------------------------------------------------------------

class TestSC09UnsignedRefuse:
    """Needs a real PSBTParser + xpriv from your test wallet."""

    @pytest.mark.skip(reason="Wire your test PSBT + xpriv")
    def test_no_signable_input_raises(self):
        # parser = PSBTParser(psbt_bytes_with_no_matching_keys)
        # signer = BitcoinCashSigner(xpriv, parser)
        # with pytest.raises(BCHSignerExpectation):
        #     signer.signed_psbt()
        pass


# ---------------------------------------------------------------------------
# SC-12 — Schnorr tag is present in source (static check)
# ---------------------------------------------------------------------------

class TestSC12SchnorrTag:

    def test_extra_entropy_string_in_module(self):
        import seedcash.models.psbt_signer as mod
        import inspect
        src = inspect.getsource(mod)
        assert "Schnorr+SHA256 " in src
        # Must not still use empty extra_entropy without the tag
        assert 'extra_entropy=b""' not in src