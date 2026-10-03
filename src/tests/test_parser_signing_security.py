"""Fail-closed parser/signing regressions (synthetic data only)."""
import hashlib
import hmac
from types import SimpleNamespace

import ecdsa
import pytest

from seedcash.models.bip44 import Bip44
from seedcash.models.psbt_parser import (
    PSBTParser, InvalidPSBT, Token, TxInput, TxOutput, ParseTransactionResult,
    parse_psbt, validate_token_prefix, read_varint,
)
from seedcash.models.psbt_signer import (
    BitcoinCashSigner, BCHSignerExpectation, parse_bip32_derivation_value,
    serialize_varint, double_sha256,
)

P2PKH = b'\x76\xa9\x14' + bytes(20) + b'\x88\xac'


def kv(key, value):
    return serialize_varint(len(key)) + key + serialize_varint(len(value)) + value


def tx_bytes(script=P2PKH):
    return (b'\x02\0\0\0\x01' + bytes(32) + bytes(4) + b'\0' + b'\xff'*4
            + b'\x01' + (900).to_bytes(8, 'little') + serialize_varint(len(script)) + script + bytes(4))


def psbt(global_extra=b'', input_map=b'', output_map=b'', script=P2PKH):
    return b'psbt\xff' + kv(b'\0', tx_bytes(script)) + global_extra + b'\0' + input_map + b'\0' + output_map + b'\0'


@pytest.mark.parametrize('path', ['m/' + '/'.join(['0']*33), 'm/-1', 'm/4294967296',
                                 "m/2147483648'", 'm/1//2', 'm/1hh', 'm/+1', 'm/١', 'm/ 1'])
def test_invalid_paths_rejected_before_derivation(path):
    with pytest.raises(ValueError):
        Bip44.parse_derivation_path(path)


def test_derivation_boundaries():
    assert Bip44.parse_derivation_path("m/2147483647'/4294967295") == [0xffffffff, 0xffffffff]
    assert len(Bip44.parse_derivation_path('m/' + '/'.join(['0']*32))) == 32
    assert parse_bip32_derivation_value(bytes(132))[1] == [0]*32
    with pytest.raises(BCHSignerExpectation):
        parse_bip32_derivation_value(bytes(136))


@pytest.mark.parametrize('index', [-1, 0x100000000, True, 1.0])
def test_child_index_rejected_before_crypto(index):
    with pytest.raises(ValueError, match='derivation index'):
        Bip44.derive_child_key(bytes(32), bytes(32), index)


def test_operation_budget_rejects_before_deriving():
    signer = BitcoinCashSigner.__new__(BitcoinCashSigner)
    signer._key_cache = {}
    signer._derivation_operations = 4096
    signer.private_key = (1).to_bytes(32, 'big')
    signer.chain_code = bytes(32)
    signer.depth = 0
    with pytest.raises(BCHSignerExpectation, match='budget'):
        signer._derive_path([0])


@pytest.mark.parametrize('suffix', [b'', b'\x80', b'\x00', b'\x40', b'\x23',
    b'\x60\x00', b'\x60\x29'+bytes(41), b'\x60\x02\x01', b'\x10\x00',
    b'\x10\xfd\x01\x00', b'\x10\xff'+(1<<63).to_bytes(8,'little')])
def test_complete_invalid_token_prefix_rejected(suffix):
    with pytest.raises(ValueError, match='token prefix'):
        validate_token_prefix(b'\xef' + bytes(32) + suffix)


def test_valid_token_commitment_and_amount_preserved():
    raw = b'\xef' + bytes(range(32)) + b'\x71\x02\xab\xcd\xfd\xfd\x00'
    token = validate_token_prefix(raw + P2PKH)
    assert token.prefix == raw
    assert token.script_pubkey == P2PKH
    assert token.ft_amount == 253
    assert token.nft_data == Token.NFTData('mutable', 'abcd')


@pytest.mark.parametrize('value', [bytes(8), bytes(8)+b'\x01', bytes(8)+b'\x00\x01',
                                  bytes(8)+b'\x01\xef'])
def test_witness_utxo_invalid_prefix_or_length_rejected(value):
    parser = PSBTParser.__new__(PSBTParser)
    with pytest.raises(ValueError):
        parser.resolve_spent_output(0, [(b'\x01', value)])


def test_valid_witness_utxo_retains_token():
    script = b'\xef'+bytes(32)+b'\x10\x01'+P2PKH
    value = (1000).to_bytes(8,'little') + serialize_varint(len(script)) + script
    parser = PSBTParser.__new__(PSBTParser)
    spent = parser.resolve_spent_output(0, [(b'\x01', value)])
    assert spent.value_satoshis == 1000
    assert spent.full_script == script
    assert spent.token.ft_amount == 1


def test_standard_v0_counts_come_from_unsigned_transaction():
    parsed = parse_psbt(psbt(global_extra=kv(b'\xfb', bytes(4))))
    assert (parsed['psbt_version'], parsed['input_count'], parsed['output_count']) == (0,1,1)


@pytest.mark.parametrize('extra', [kv(b'\xfb', b'\x02\0\0\0'), kv(b'\x04', b'\x01'),
                                    kv(b'\0\x01', tx_bytes())])
def test_unsupported_version_and_invalid_global_fields_rejected(extra):
    with pytest.raises(ValueError):
        parse_psbt(psbt(global_extra=extra))


@pytest.mark.parametrize('output_map', [kv(b'\x03',bytes(8)), kv(b'\x04',P2PKH),
    kv(b'\x7f',b''), kv(b'\x00',b'\x51')*2])
def test_v0_invalid_output_fields_rejected(output_map):
    with pytest.raises(ValueError):
        parse_psbt(psbt(output_map=output_map))


def test_duplicate_unsigned_transaction_rejected():
    with pytest.raises(ValueError, match='duplicate'):
        parse_psbt(psbt(global_extra=kv(b'\0',tx_bytes())))


def test_parser_boundary_returns_controlled_failure():
    with pytest.raises(InvalidPSBT):
        PSBTParser(None)
    with pytest.raises(InvalidPSBT):
        PSBTParser(psbt())  # missing UTXO


def test_negative_compactsize_offset_rejected():
    with pytest.raises(ValueError):
        read_varint(b'\x01', -1)


def signing_tx(script):
    spent = TxOutput(1000, full_script=script)
    return ParseTransactionResult(b'\x02\0\0\0',
        [TxInput(bytes(32),0,0xffffffff,spent_output=spent)],
        [TxOutput(900,full_script=P2PKH)],bytes(4))


@pytest.mark.parametrize('p2sh32',[False,True])
def test_p2sh_requires_matching_redeem_script_and_signs_redeem(p2sh32):
    signer = BitcoinCashSigner.__new__(BitcoinCashSigner)
    redeem = b'\x51'
    locking = ((b'\xaa\x20'+double_sha256(redeem)) if p2sh32
               else (b'\xa9\x14'+Bip44.hash160(redeem))) + b'\x87'
    transaction = signing_tx(locking)
    with pytest.raises(BCHSignerExpectation, match='missing redeem'):
        signer.create_sighash(transaction,0)
    with pytest.raises(BCHSignerExpectation, match='does not match'):
        signer.create_sighash(transaction,0,script_code=b'\x52')
    actual = signer.create_sighash(transaction,0,script_code=redeem)
    # Independent BIP143 construction commits to the redeem bytes, not P2SH.
    preimage = (transaction.version + double_sha256(bytes(36))
        + double_sha256(b'\xff'*4) + bytes(36) + b'\x01'+redeem
        + (1000).to_bytes(8,'little') + b'\xff'*4
        + double_sha256((900).to_bytes(8,'little')+bytes([len(P2PKH)])+P2PKH)
        + bytes(4) + b'\x41\0\0\0')
    assert actual == double_sha256(preimage)


def test_p2pkh_sighash_default_unchanged():
    signer = BitcoinCashSigner.__new__(BitcoinCashSigner)
    transaction = signing_tx(P2PKH)
    assert signer.create_sighash(transaction,0) == signer.create_sighash(transaction,0,script_code=P2PKH)


def test_schnorr_bch_challenge_and_quadratic_residue():
    # Independently verify the BCH equation; BIP340/even-Y would fail this check.
    signer = BitcoinCashSigner.__new__(BitcoinCashSigner)
    key = (1).to_bytes(32,'big')
    public = Bip44.private_to_public(key)
    message = hashlib.sha256(b'SeedCash synthetic BCH test').digest()
    signature = signer._sign_schnorr(key,message,public)
    assert len(signature) == 64
    r = int.from_bytes(signature[:32],'big')
    s = int.from_bytes(signature[32:],'big')
    challenge = int.from_bytes(hashlib.sha256(signature[:32]+public+message).digest(),'big') % ecdsa.SECP256k1.order
    point = s*ecdsa.SECP256k1.generator + (-challenge % ecdsa.SECP256k1.order)*ecdsa.VerifyingKey.from_string(public,curve=ecdsa.SECP256k1).pubkey.point
    prime = ecdsa.SECP256k1.curve.p()
    assert point.x() == r
    assert pow(point.y(),(prime-1)//2,prime) == 1
    # Independent RFC6979 initialization verifies the exact 16-byte nonce domain.
    seed = key + message + b'Schnorr+SHA256  '
    state, value = bytes(32), b'\x01'*32
    state = hmac.new(state,value+b'\0'+seed,hashlib.sha256).digest()
    value = hmac.new(state,value,hashlib.sha256).digest()
    state = hmac.new(state,value+b'\x01'+seed,hashlib.sha256).digest()
    value = hmac.new(state,value,hashlib.sha256).digest()
    nonce = int.from_bytes(hmac.new(state,value,hashlib.sha256).digest(),'big')
    expected_point = nonce*ecdsa.SECP256k1.generator
    if pow(expected_point.y(),(prime-1)//2,prime) != 1:
        nonce = ecdsa.SECP256k1.order-nonce
    expected = expected_point.x().to_bytes(32,'big')+((nonce+challenge)%ecdsa.SECP256k1.order).to_bytes(32,'big')
    assert signature == expected


@pytest.mark.parametrize('key,message,public', [(bytes(32),bytes(32),b'\x02'+bytes(32)),
    ((1).to_bytes(32,'big'),bytes(31),Bip44.private_to_public((1).to_bytes(32,'big'))),
    ((1).to_bytes(32,'big'),bytes(32),Bip44.private_to_public((2).to_bytes(32,'big')))])
def test_invalid_schnorr_inputs_rejected(key,message,public):
    with pytest.raises(BCHSignerExpectation):
        BitcoinCashSigner.__new__(BitcoinCashSigner)._sign_schnorr(key,message,public)


def test_v145_output_metadata_must_match_signed_transaction():
    globals_145 = kv(b'\xfb',b'\x91')+kv(b'\x04',b'\x01')+kv(b'\x05',b'\x01')
    for field in [kv(b'\x03',bytes(7)), kv(b'\x03',(901).to_bytes(8,'little')),
                  kv(b'\x04',b'\x6a'), kv(b'\x36',b'\xef'+bytes(32)+b'\x10\x01')]:
        with pytest.raises(ValueError):
            parse_psbt(psbt(global_extra=globals_145,output_map=field))


def test_token_unknown_locking_bytecode_fails_closed():
    with pytest.raises(InvalidPSBT):
        PSBTParser(psbt(script=b'\xef'+bytes(32)+b'\x10\x01\x51'))


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


def test_conflicting_non_witness_and_witness_utxos_rejected():
    parent = tx_bytes()
    txid = double_sha256(parent)
    witness = (901).to_bytes(8,'little') + bytes([len(P2PKH)]) + P2PKH
    parser = PSBTParser.__new__(PSBTParser)
    with pytest.raises(ValueError, match='conflicting'):
        parser.resolve_spent_output(0, [(b'\0',parent),(b'\x01',witness)], txid)
