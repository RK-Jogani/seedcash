"""Focused tests for current SeedCash APIs; synthetic data only."""
from pathlib import Path
import pytest
from seedcash.models.psbt_parser import classify_script
from seedcash.models.psbt_parser import ScriptType
from seedcash.models.psbt_parser import parse_transaction
from seedcash.models.psbt_parser import ParseTransactionResult
from seedcash.models.psbt_parser import Token
from seedcash.models.psbt_parser import TxInput
from seedcash.models.psbt_parser import TxOutput
from seedcash.models.psbt_parser import PSBTParser
from seedcash.models.psbt_signer import BitcoinCashSigner
from seedcash.models.psbt_signer import BCHSignerExpectation
from seedcash.models.psbt_signer import SIGHASH_ALL
from seedcash.models.psbt_signer import SIGHASH_FORKID
from seedcash.models.psbt_signer import SIGHASH_NONE
from seedcash.models.psbt_signer import double_sha256
from seedcash.models.psbt_signer import validate_redeem_script
from seedcash.models.psbt_signer import validate_multisig_redeem_script
from seedcash.models.bip44 import Bip44
from seedcash.models.psbt_signer import ALLOWED_SIGHASH
from seedcash.models.psbt_signer import SIGHASH_ANYONECANPAY
from seedcash.models.psbt_signer import SIGHASH_UTXOS
from seedcash.models.psbt_parser import parse_token_script
import hashlib
import hmac
from types import SimpleNamespace
import ecdsa
from seedcash.models.psbt_parser import parse_psbt
from seedcash.models.psbt_parser import read_varint
from seedcash.models.psbt_signer import parse_bip32_derivation_value
from seedcash.models.psbt_signer import serialize_varint
from seedcash.models.psbt_parser import parse_keypairs
import json

def audit_integration__varint(n: int) -> bytes:
    if n < 253:
        return bytes([n])
    if n <= 65535:
        return b'\xfd' + n.to_bytes(2, 'little')
    raise ValueError('varint too large for this helper')

def audit_integration__p2pkh_script(h160: bytes=None) -> bytes:
    h160 = h160 or bytes(20)
    return b'v\xa9\x14' + h160 + b'\x88\xac'

def audit_integration__op_return_script(payload: bytes=b'test') -> bytes:
    return b'j' + bytes([len(payload)]) + payload

def audit_integration_build_tx(outputs: list[tuple[int, bytes]]) -> bytes:
    """
    Minimal legacy BCH tx:
      version(4) | vin_count=0 | vout_count | outs... | locktime(4)
    Enough for parse_transaction output classification.
    """
    body = b'\x01\x00\x00\x00'
    body += audit_integration__varint(0)
    body += audit_integration__varint(len(outputs))
    for (value_sats, script) in outputs:
        body += value_sats.to_bytes(8, 'little')
        body += audit_integration__varint(len(script)) + script
    body += b'\x00\x00\x00\x00'
    return body

class TestAuditIntegration:

    class TestSC02OpReturnFirst:

        def test_parse_op_return_then_p2pkh(self):
            """
        Audit fixture A shape:
          v0 = 8_998_000 OP_RETURN
          v1 = 1_001_000 P2PKH Alice
        Payment list must be Alice only; amount for Alice is 1_001_000.
        """
            alice_h160 = bytes.fromhex('cbdd214121b18cac291e41175e5b9204b9df7457')
            tx = audit_integration_build_tx([(8998000, audit_integration__op_return_script(b'burn')), (1001000, audit_integration__p2pkh_script(alice_h160))])
            result = parse_transaction(tx)
            assert len(result.outputs) == 2
            assert result.outputs[0].script_type == ScriptType.OP_RETURN
            assert result.outputs[0].address is None
            assert result.outputs[0].value_satoshis == 8998000
            assert result.outputs[1].script_type == ScriptType.P2PKH
            assert result.outputs[1].address is not None
            assert result.outputs[1].value_satoshis == 1001000
            payment = [o for o in result.outputs if o.address]
            assert len(payment) == 1
            assert payment[0].value_satoshis == 1001000
            assert payment[0].index == 1

    class TestSC03OnParsedTx:

        def test_lookalike_output_has_no_address(self):
            alice = bytes.fromhex('cbdd214121b18cac291e41175e5b9204b9df7457')
            attacker = bytes.fromhex('11' * 20)
            lookalike = b'v\xa9\x14' + alice + b'm' + b'v\xa9\x14' + attacker + b'\x88\xac'
            tx = audit_integration_build_tx([(9000000, lookalike)])
            with pytest.raises(ValueError, match='unknown script type'):
                parse_transaction(tx)

    class TestSC01SighashRuntime:

        def test_none_forkid_not_allowed_constant(self):
            from seedcash.models.psbt_signer import ALLOWED_SIGHASH
            assert SIGHASH_NONE | SIGHASH_FORKID not in ALLOWED_SIGHASH
            assert SIGHASH_ALL | SIGHASH_FORKID in ALLOWED_SIGHASH

        def test_genesis_accepts_tokenized_vout_zero_input(self):
            category_id = '11' * 32
            spent_category_id = '22' * 32
            prev_txid = bytes.fromhex(category_id)[::-1]
            token = Token(prefix=b'', script_pubkey=audit_integration__p2pkh_script(), category_id=spent_category_id, ft_amount=1)
            spent_output = TxOutput(value_satoshis=1000, index=0, full_script=token.script_pubkey, token=token)
            tx_input = TxInput(prev_txid=prev_txid, prev_index=0, sequence=0)
            parser = PSBTParser.__new__(PSBTParser)
            parser.parsed = {'inputs': [[]]}
            parser.total_input_amount = 0
            parser.total_output_amount = 0
            parser.categories = {'nft': [], 'ft': []}
            parser.tx = ParseTransactionResult(version=b'\x01\x00\x00\x00', inputs=[tx_input], outputs=[TxOutput(value_satoshis=900, index=0, full_script=token.script_pubkey, token=Token(prefix=b'', script_pubkey=token.script_pubkey, category_id=category_id, ft_amount=1))], locktime=b'\x00\x00\x00\x00')
            parser.resolve_spent_output = lambda prev_index, input_pairs, prev_txid=None: spent_output
            parser.build_transaction()
            assert parser.genesis is not None
            assert category_id in parser.genesis.categories['ft']

    class TestRedeemScriptValidation:

        def test_standard_multisig_redeem_script_is_accepted(self):
            redeem_script = b'R' + b'!\x02' + bytes(32) + b'!\x03' + bytes(32) + b'R\xae'
            assert validate_multisig_redeem_script(redeem_script) == (redeem_script, [b'\x02' + bytes(32), b'\x03' + bytes(32)])

        @pytest.mark.parametrize('redeem_script', [b'Q', b'Q!' + bytes(33) + b'Q\xae', b'Q ' + bytes(32) + b'Q\xae', b'R!\x02' + bytes(32) + b'Q\xae', b'Q!\x02' + bytes(32) + b'R\xae', b'Q!\x02' + bytes(32) + b'Q\xae\x00'])
        def test_nonstandard_multisig_redeem_script_is_rejected(self, redeem_script):
            with pytest.raises(BCHSignerExpectation, match='redeem script'):
                validate_multisig_redeem_script(redeem_script)

        def test_matching_p2sh20_redeem_script_is_accepted(self):
            redeem_script = b'Q'
            script_pubkey = b'\xa9\x14' + Bip44.hash160(redeem_script) + b'\x87'
            assert validate_redeem_script(script_pubkey, redeem_script) == redeem_script

        def test_mismatched_redeem_script_is_rejected(self):
            redeem_script = b'Q'
            script_pubkey = b'\xa9\x14' + Bip44.hash160(redeem_script) + b'\x87'
            with pytest.raises(BCHSignerExpectation, match='does not match'):
                validate_redeem_script(script_pubkey, b'R')

        def test_matching_p2sh32_redeem_script_is_accepted(self):
            redeem_script = b'Q'
            script_pubkey = b'\xaa ' + double_sha256(redeem_script) + b'\x87'
            assert validate_redeem_script(script_pubkey, redeem_script) == redeem_script

    class TestSC06Units:

        def test_sats_to_bch(self):
            """1 BCH = 1e8 sats. Display must use /1e8, not /1e6."""
            sats = 100000000
            bch = sats / 100000000.0
            wrong = sats / 1000000.0
            assert bch == 1.0
            assert wrong == 100.0

class TestAuditSc01Sc05:

    class TestSC01Sighash:

        def test_allowed_all_forkid(self):
            assert SIGHASH_ALL | SIGHASH_FORKID in ALLOWED_SIGHASH

        def test_allowed_all_forkid_utxos(self):
            assert SIGHASH_ALL | SIGHASH_FORKID | SIGHASH_UTXOS in ALLOWED_SIGHASH

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

    class TestSC03Lookalike:

        def test_standard_p2pkh_ok(self):
            h160 = bytes.fromhex('cbdd214121b18cac291e41175e5b9204b9df7457')
            script = b'v\xa9\x14' + h160 + b'\x88\xac'
            assert len(script) == 25
            (stype, addr) = classify_script(script)
            assert stype == ScriptType.P2PKH
            assert addr is not None
            assert addr.startswith('bitcoincash:q')

        def test_long_lookalike_rejected(self):
            """startswith/endswith only would accept this; len must be 25."""
            h160 = bytes.fromhex('cbdd214121b18cac291e41175e5b9204b9df7457')
            script = b'v\xa9\x14' + h160 + b'\x88\xac' + b'\x00' * 10
            assert len(script) != 25
            (stype, addr) = classify_script(script)
            assert stype != ScriptType.P2PKH
            assert addr is None

        def test_op2drop_lookalike_rejected(self):
            """
        Audit construction (~49 bytes):
        DUP HASH160 PUSH20(alice) OP_2DROP
        DUP HASH160 PUSH20(attacker) EQUALVERIFY CHECKSIG
        Must NOT display as Alice P2PKH.
        """
            alice = bytes.fromhex('cbdd214121b18cac291e41175e5b9204b9df7457')
            attacker = bytes.fromhex('11' * 20)
            script = b'v\xa9\x14' + alice + b'm' + b'v\xa9\x14' + attacker + b'\x88\xac'
            assert len(script) != 25
            (stype, addr) = classify_script(script)
            assert stype != ScriptType.P2PKH
            assert addr is None

        def test_p2pk_compressed(self):
            script = b'!' + b'\x02' + b'\x11' * 32 + b'\xac'
            assert len(script) == 35
            (stype, addr) = classify_script(script)
            assert stype == ScriptType.P2PK
            assert addr is None

        def test_p2pk_uncompressed(self):
            script = b'A' + b'\x04' + b'\x11' * 64 + b'\xac'
            assert len(script) == 67
            (stype, addr) = classify_script(script)
            assert stype == ScriptType.P2PK
            assert addr is None

        def test_op_return_no_address(self):
            script = b'j\x04test'
            (stype, addr) = classify_script(script)
            assert stype == ScriptType.OP_RETURN
            assert addr is None

    class TestSC02Pairing:

        def test_bch_outputs_only_have_address(self):
            scripts = [b'j\x04dead', b'v\xa9\x14' + bytes(20) + b'\x88\xac']
            addrs = []
            for s in scripts:
                (stype, addr) = classify_script(s)
                if addr:
                    addrs.append(addr)
            assert len(addrs) == 1

        def test_op_return_and_p2pk_filtered(self):
            items = [(ScriptType.OP_RETURN, None), (ScriptType.P2PK, None), (ScriptType.P2PKH, 'bitcoincash:q...')]
            payment = [addr for (st, addr) in items if addr]
            assert len(payment) == 1

    class TestSC04SC05Tokens:

        def test_token_prefix_rejected_reserved_bit(self):
            script = b'\xef' + bytes(32) + b'\x80'
            assert parse_token_script(script) is None

        def test_token_prefix_rejects_invalid_parameters(self):
            category = bytes(32)
            assert parse_token_script(b'\xef' + category + b'\x13') is None
            assert parse_token_script(b'\xef' + category + b'@\x01') is None
            assert parse_token_script(b'\xef' + category + b'`\xfd') is None
            assert parse_token_script(b'\xef' + category + b'\x10\x00') is None
            assert parse_token_script(b'\xef' + category + b'\x10\xfd\x01\x00') is None

        def test_token_prefix_accepts_valid_nft_and_ft(self):
            category = bytes(32)
            nft = b'\xef' + category + b'`\x01x'
            ft = b'\xef' + category + b'\x10\x01'
            assert parse_token_script(nft) is not None
            assert parse_token_script(ft) is not None

        def test_plain_script_not_token(self):
            assert parse_token_script(b'v\xa9\x14' + bytes(20) + b'\x88\xac') is None
parser_signing_security_P2PKH = b'v\xa9\x14' + bytes(20) + b'\x88\xac'

def parser_signing_security_kv(key, value):
    return serialize_varint(len(key)) + key + serialize_varint(len(value)) + value

def parser_signing_security_tx_bytes(script=parser_signing_security_P2PKH):
    return b'\x02\x00\x00\x00\x01' + bytes(32) + bytes(4) + b'\x00' + b'\xff' * 4 + b'\x01' + 900 .to_bytes(8, 'little') + serialize_varint(len(script)) + script + bytes(4)

def parser_signing_security_psbt(global_extra=b'', input_map=b'', output_map=b'', script=parser_signing_security_P2PKH):
    return b'psbt\xff' + parser_signing_security_kv(b'\x00', parser_signing_security_tx_bytes(script)) + global_extra + b'\x00' + input_map + b'\x00' + output_map + b'\x00'

def parser_signing_security_signing_tx(script):
    spent = TxOutput(1000, full_script=script)
    return ParseTransactionResult(b'\x02\x00\x00\x00', [TxInput(bytes(32), 0, 4294967295, spent_output=spent)], [TxOutput(900, full_script=parser_signing_security_P2PKH)], bytes(4))

class TestParserSigningSecurity:

    @staticmethod
    @pytest.mark.parametrize('path', ['m/' + '/'.join(['0'] * 33), 'm/-1', 'm/4294967296', "m/2147483648'", 'm/1//2', 'm/1hh', 'm/+1', 'm/١', 'm/ 1'])
    def test_invalid_paths_rejected_before_derivation(path):
        with pytest.raises(ValueError):
            Bip44.parse_derivation_path(path)

    @staticmethod
    def test_derivation_boundaries():
        assert Bip44.parse_derivation_path("m/2147483647'/4294967295") == [4294967295, 4294967295]
        assert len(Bip44.parse_derivation_path('m/' + '/'.join(['0'] * 32))) == 32
        assert parse_bip32_derivation_value(bytes(132))[1] == [0] * 32
        with pytest.raises(BCHSignerExpectation):
            parse_bip32_derivation_value(bytes(136))

    @staticmethod
    @pytest.mark.parametrize('index', [-1, 4294967296, True, 1.0])
    def test_child_index_rejected_before_crypto(index):
        with pytest.raises(ValueError, match='derivation index'):
            Bip44.derive_child_key(bytes(32), bytes(32), index)

    @staticmethod
    @pytest.mark.parametrize('suffix', [b'', b'\x80', b'\x00', b'@', b'#', b'`\x00', b'`)' + bytes(41), b'`\x02\x01', b'\x10\x00', b'\x10\xfd\x01\x00', b'\x10\xff' + (1 << 63).to_bytes(8, 'little')])
    def test_complete_invalid_token_prefix_rejected(suffix):
        try:
            token = parse_token_script(b'\xef' + bytes(32) + suffix)
        except ValueError:
            return
        assert token is None, 'Malformed token prefix was accepted'

    @staticmethod
    def test_valid_token_commitment_and_amount_preserved():
        raw = b'\xef' + bytes(range(32)) + b'q\x02\xab\xcd\xfd\xfd\x00'
        token = parse_token_script(raw + parser_signing_security_P2PKH)
        assert token.prefix == raw
        assert token.script_pubkey == parser_signing_security_P2PKH
        assert token.ft_amount == 253
        assert token.nft_data == Token.NFTData('mutable', 'abcd')

    @staticmethod
    @pytest.mark.parametrize('value', [bytes(8), bytes(8) + b'\x01', bytes(8) + b'\x00\x01', bytes(8) + b'\x01\xef'])
    def test_witness_utxo_invalid_prefix_or_length_rejected(value):
        parser = PSBTParser.__new__(PSBTParser)
        with pytest.raises(ValueError):
            parser.resolve_spent_output(0, [(b'\x01', value)])

    @staticmethod
    def test_valid_witness_utxo_retains_token():
        script = b'\xef' + bytes(32) + b'\x10\x01' + parser_signing_security_P2PKH
        value = 1000 .to_bytes(8, 'little') + serialize_varint(len(script)) + script
        parser = PSBTParser.__new__(PSBTParser)
        spent = parser.resolve_spent_output(0, [(b'\x01', value)])
        assert spent.value_satoshis == 1000
        assert spent.full_script == script
        assert spent.token.ft_amount == 1

    @staticmethod
    def test_standard_v0_counts_come_from_unsigned_transaction():
        parsed = parse_psbt(parser_signing_security_psbt(global_extra=parser_signing_security_kv(b'\xfb', bytes(4))))
        assert (parsed['psbt_version'], parsed['input_count'], parsed['output_count']) == (0, 1, 1)

    @staticmethod
    @pytest.mark.parametrize('extra', [parser_signing_security_kv(b'\xfb', b'\x02\x00\x00\x00'), parser_signing_security_kv(b'\x04', b'\x01'), parser_signing_security_kv(b'\x00\x01', parser_signing_security_tx_bytes())])
    def test_unsupported_version_and_invalid_global_fields_rejected(extra):
        with pytest.raises(ValueError):
            parse_psbt(parser_signing_security_psbt(global_extra=extra))

    @staticmethod
    @pytest.mark.parametrize('output_map', [parser_signing_security_kv(b'\x03', bytes(8)), parser_signing_security_kv(b'\x04', parser_signing_security_P2PKH), parser_signing_security_kv(b'\x7f', b''), parser_signing_security_kv(b'\x00', b'Q') * 2])
    def test_v0_invalid_output_fields_rejected(output_map):
        with pytest.raises(ValueError):
            parse_psbt(parser_signing_security_psbt(output_map=output_map))

    @staticmethod
    def test_duplicate_unsigned_transaction_rejected():
        with pytest.raises(ValueError, match='duplicate'):
            parse_psbt(parser_signing_security_psbt(global_extra=parser_signing_security_kv(b'\x00', parser_signing_security_tx_bytes())))

    @staticmethod
    def test_parser_boundary_returns_controlled_failure():
        with pytest.raises(TypeError):
            PSBTParser(None)
        with pytest.raises(ValueError):
            PSBTParser(parser_signing_security_psbt())

    @staticmethod
    def test_negative_compactsize_offset_rejected():
        with pytest.raises(ValueError):
            read_varint(b'\x01', -1)

    @staticmethod
    @pytest.mark.parametrize('p2sh32', [False, True])
    def test_matching_redeem_script_produces_independent_bip143_digest(p2sh32):
        signer = BitcoinCashSigner.__new__(BitcoinCashSigner)
        redeem = b'Q'
        locking = (b'\xaa ' + double_sha256(redeem) if p2sh32 else b'\xa9\x14' + Bip44.hash160(redeem)) + b'\x87'
        transaction = parser_signing_security_signing_tx(locking)
        with pytest.raises((ValueError, BCHSignerExpectation)):
            validate_redeem_script(locking, b'R')
        validate_redeem_script(locking, redeem)
        actual = signer.create_sighash(transaction, 0, script_code=redeem)
        preimage = transaction.version + double_sha256(bytes(36)) + double_sha256(b'\xff' * 4) + bytes(36) + b'\x01' + redeem + 1000 .to_bytes(8, 'little') + b'\xff' * 4 + double_sha256(900 .to_bytes(8, 'little') + bytes([len(parser_signing_security_P2PKH)]) + parser_signing_security_P2PKH) + bytes(4) + b'A\x00\x00\x00'
        assert actual == double_sha256(preimage)

    @staticmethod
    def test_p2pkh_sighash_default_unchanged():
        signer = BitcoinCashSigner.__new__(BitcoinCashSigner)
        transaction = parser_signing_security_signing_tx(parser_signing_security_P2PKH)
        assert signer.create_sighash(transaction, 0) == signer.create_sighash(transaction, 0, script_code=parser_signing_security_P2PKH)

    @staticmethod
    def test_schnorr_bch_challenge_and_quadratic_residue():
        signer = BitcoinCashSigner.__new__(BitcoinCashSigner)
        key = 1 .to_bytes(32, 'big')
        public = Bip44.private_to_public(key)
        message = hashlib.sha256(b'SeedCash synthetic BCH test').digest()
        signature = signer._sign_schnorr(key, message, public)
        assert len(signature) == 64
        r = int.from_bytes(signature[:32], 'big')
        s = int.from_bytes(signature[32:], 'big')
        challenge = int.from_bytes(hashlib.sha256(signature[:32] + public + message).digest(), 'big') % ecdsa.SECP256k1.order
        point = s * ecdsa.SECP256k1.generator + -challenge % ecdsa.SECP256k1.order * ecdsa.VerifyingKey.from_string(public, curve=ecdsa.SECP256k1).pubkey.point
        prime = ecdsa.SECP256k1.curve.p()
        assert point.x() == r
        assert pow(point.y(), (prime - 1) // 2, prime) == 1
        seed = key + message + b'Schnorr+SHA256  '
        (state, value) = (bytes(32), b'\x01' * 32)
        state = hmac.new(state, value + b'\x00' + seed, hashlib.sha256).digest()
        value = hmac.new(state, value, hashlib.sha256).digest()
        state = hmac.new(state, value + b'\x01' + seed, hashlib.sha256).digest()
        value = hmac.new(state, value, hashlib.sha256).digest()
        nonce = int.from_bytes(hmac.new(state, value, hashlib.sha256).digest(), 'big')
        expected_point = nonce * ecdsa.SECP256k1.generator
        if pow(expected_point.y(), (prime - 1) // 2, prime) != 1:
            nonce = ecdsa.SECP256k1.order - nonce
        expected = expected_point.x().to_bytes(32, 'big') + ((nonce + challenge) % ecdsa.SECP256k1.order).to_bytes(32, 'big')
        assert signature == expected

    @staticmethod
    @pytest.mark.parametrize('key,message,public', [(bytes(32), bytes(32), b'\x02' + bytes(32)), (1 .to_bytes(32, 'big'), bytes(31), Bip44.private_to_public(1 .to_bytes(32, 'big'))), (1 .to_bytes(32, 'big'), bytes(32), Bip44.private_to_public(2 .to_bytes(32, 'big')))])
    def test_invalid_schnorr_inputs_rejected(key, message, public):
        with pytest.raises(BCHSignerExpectation):
            BitcoinCashSigner.__new__(BitcoinCashSigner)._sign_schnorr(key, message, public)

    @staticmethod
    def test_v145_output_metadata_must_match_signed_transaction():
        globals_145 = parser_signing_security_kv(b'\xfb', b'\x91') + parser_signing_security_kv(b'\x04', b'\x01') + parser_signing_security_kv(b'\x05', b'\x01')
        for field in [parser_signing_security_kv(b'\x03', bytes(7)), parser_signing_security_kv(b'\x03', 901 .to_bytes(8, 'little')), parser_signing_security_kv(b'\x04', b'j'), parser_signing_security_kv(b'6', b'\xef' + bytes(32) + b'\x10\x01')]:
            with pytest.raises(ValueError):
                parse_psbt(parser_signing_security_psbt(global_extra=globals_145, output_map=field))

    @staticmethod
    def test_token_unknown_locking_bytecode_fails_closed():
        with pytest.raises(ValueError):
            PSBTParser(parser_signing_security_psbt(script=b'\xef' + bytes(32) + b'\x10\x01Q'))

    @staticmethod
    def test_signer_clears_keys_on_early_failure():
        signer = BitcoinCashSigner.__new__(BitcoinCashSigner)
        signer.private_key = bytes(32)
        signer.chain_code = bytes(32)
        signer._key_cache = {'synthetic': (bytes(32), bytes(33))}
        signer.parser = SimpleNamespace(tx=None)
        with pytest.raises(BCHSignerExpectation, match='No unsigned'):
            signer.signed_psbt()
        assert signer.private_key is None
        assert signer.chain_code is None
        assert signer._key_cache == {}

    @staticmethod
    def test_conflicting_non_witness_and_witness_utxos_rejected():
        parent = parser_signing_security_tx_bytes()
        txid = double_sha256(parent)
        witness = 901 .to_bytes(8, 'little') + bytes([len(parser_signing_security_P2PKH)]) + parser_signing_security_P2PKH
        parser = PSBTParser.__new__(PSBTParser)
        with pytest.raises(ValueError, match='conflicting'):
            parser.resolve_spent_output(0, [(b'\x00', parent), (b'\x01', witness)], txid)

class TestPsbtParserBoundaries:

    @staticmethod
    def test_non_minimal_compact_size_is_rejected():
        with pytest.raises(ValueError, match='non-minimal'):
            read_varint(b'\xfd\x01\x00', 0)

    @staticmethod
    def test_truncated_compact_size_is_rejected():
        with pytest.raises(ValueError, match='truncated'):
            read_varint(b'\xfe\x01\x00', 0)

    @staticmethod
    def test_duplicate_key_in_map_is_rejected():
        encoded = b'\x01\x01\x00' + b'\x01\x01\x00' + b'\x00'
        with pytest.raises(ValueError, match='duplicate'):
            parse_keypairs(encoded, 0)

    @staticmethod
    def test_trailing_transaction_bytes_are_rejected():
        transaction = b'\x01\x00\x00\x00' + b'\x00' + b'\x00' + b'\x00\x00\x00\x00' + b'\x00'
        with pytest.raises(ValueError, match='trailing'):
            parse_transaction(transaction + b'\x00')

    @staticmethod
    def test_unknown_global_field_is_rejected():
        psbt = b'psbt\xff' + b'\x01\x7f\x00' + b'\x00'
        with pytest.raises(ValueError, match='unknown PSBT global field'):
            parse_psbt(psbt)
psbt_v145_cashtoken_scenarios_FIXTURE_PATH = Path(__file__).with_name('psbtV145CashTokenScenarios.json')

def psbt_v145_cashtoken_scenarios_load_fixture():
    return json.loads(psbt_v145_cashtoken_scenarios_FIXTURE_PATH.read_text())

class TestPsbtV145CashtokenScenarios:

    @staticmethod
    def test_materialized_fixtures_match_declared_transaction_contract():
        fixture = psbt_v145_cashtoken_scenarios_load_fixture()
        assert len(fixture['materializedFixtures']) == fixture['materializedFixtureCount']
        for materialized in fixture['materializedFixtures']:
            for parent in materialized['sourceTransactions']:
                digest = hashlib.sha256(hashlib.sha256(bytes.fromhex(parent['hex'])).digest()).digest()
                assert digest[::-1].hex() == parent['txid']
            parser = PSBTParser(bytearray.fromhex(materialized['psbtHex']))
            assert parser.parsed['unsigned_tx'].hex() == materialized['unsignedTransactionHex']
            assert parser.input_count == len(materialized['inputs'])
            assert parser.output_count == len(materialized['outputs'])
            assert parser.input_amount == sum((int(parent_output['satoshis']) for parent in materialized['sourceTransactions'] for parent_output in parent['outputs'] if any((tx_input['txid'] == parent['txid'] and tx_input['vout'] == parent['outputs'].index(parent_output) for tx_input in materialized['inputs']))))
            assert parser.output_amount == sum((int(output['satoshis']) for output in materialized['outputs']))

    @staticmethod
    @pytest.mark.parametrize('vector', psbt_v145_cashtoken_scenarios_load_fixture()['materializedNegativeVectors'])
    def test_materialized_negative_vectors_are_rejected(vector):
        with pytest.raises(ValueError):
            PSBTParser(bytearray.fromhex(vector['psbtHex']))
sc07_cashaddr_H160 = bytes.fromhex('f5bf48b397dac9') + bytes(13)
sc07_cashaddr_H160 = bytes.fromhex('f5bf48b397dac918a1fe95962deb1a885b7834f9')

class TestSc07Cashaddr:

    class TestSC07CashAddr:

        def test_plain_p2pkh_is_q(self):
            addr = Bip44.hash160_to_cashaddr(sc07_cashaddr_H160, version_byte=0)
            assert ':q' in addr or addr.split(':')[1].startswith('q')

        def test_token_p2pkh_is_z(self):
            addr = Bip44.hash160_to_cashaddr(sc07_cashaddr_H160, version_byte=16)
            assert addr.split(':')[1].startswith('z')

        def test_plain_p2sh20_is_p(self):
            addr = Bip44.hash160_to_cashaddr(sc07_cashaddr_H160, version_byte=8)
            assert addr.split(':')[1].startswith('p')

        def test_token_p2sh_version(self):
            addr = Bip44.hash160_to_cashaddr(sc07_cashaddr_H160, version_byte=24)
            assert addr.split(':')[1].startswith('r')

        def test_classify_token_p2pkh_uses_token_version(self):
            script = b'v\xa9\x14' + sc07_cashaddr_H160 + b'\x88\xac'
            (stype, addr) = classify_script(script, is_token_tx=True)
            assert stype == ScriptType.P2PKH
            assert addr is not None
            assert addr.split(':')[1].startswith('z')

        def test_classify_plain_p2pkh_is_q(self):
            script = b'v\xa9\x14' + sc07_cashaddr_H160 + b'\x88\xac'
            (stype, addr) = classify_script(script, is_token_tx=False)
            assert stype == ScriptType.P2PKH
            assert addr.split(':')[1].startswith('q')
