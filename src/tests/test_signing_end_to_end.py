"""Public synthetic raw bytes -> rendered review args -> BIP143 -> BCH signature."""
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import ecdsa
import pytest

from seedcash.models.bip44 import Bip44
from seedcash.models.psbt_parser import PSBTParser, parse_psbt, parse_transaction
from seedcash.models.psbt_signer import BitcoinCashSigner, double_sha256, serialize_varint, _serialize_keypairs
from seedcash.models.token_review import TokenReview
from seedcash.views import psbt_views as views


def transaction(inputs, outputs):
    raw = b'\x02\0\0\0' + serialize_varint(len(inputs))
    for txid, index in inputs:
        raw += txid + index.to_bytes(4, 'little') + b'\0' + b'\xff' * 4
    raw += serialize_varint(len(outputs))
    for sats, script in outputs:
        raw += sats.to_bytes(8, 'little') + serialize_varint(len(script)) + script
    return raw + bytes(4)


def test_raw_bytes_ui_review_preimage_signature_and_ur_agree(monkeypatch):
    # Deterministic account key for this public test fixture only.
    key, chain = (1).to_bytes(32, 'big'), bytes(range(32))
    xpriv = Bip44.xpriv_encode(b'\x03', bytes(4), b'\x80\0\0\0', chain, key)
    path = [0x8000002c, 0x80000091, 0x80000000, 0, 0]
    child, child_chain = Bip44.derive_child_key(key, chain, 0)
    child, _ = Bip44.derive_child_key(child, child_chain, 0)
    pub = Bip44.private_to_public(child)
    locking = b'\x76\xa9\x14' + Bip44.hash160(pub) + b'\x88\xac'
    category = bytes(range(32))
    # Mutable NFT, commitment 01 -> 02, plus FT burn 10 -> 7.
    token_input = b'\xef' + category + b'\x71\x01\x01\x0a'
    token_output = b'\xef' + category + b'\x71\x01\x02\x07'
    parent = transaction([(bytes(32), 1)], [(1000, token_input + locking)])
    txid = double_sha256(parent)
    outputs = [(0, b'\x6a\x03abc'), (900, token_output + locking)]
    unsigned = transaction([(txid, 0)], outputs)
    derivation = bytes(4) + b''.join(index.to_bytes(4, 'little') for index in path)
    globals_ = [(b'\x00', unsigned)]
    inputs = [(b'\x00', parent), (b'\x06' + pub, derivation)]
    raw_psbt = (b'psbt\xff' + _serialize_keypairs(globals_) + b'\0'
                + _serialize_keypairs(inputs) + b'\0' + b'\0\0')
    parser = PSBTParser(raw_psbt)
    review = TokenReview.from_parser(parser)
    c = review.categories[0]
    assert (c.category_id, c.input_amount, c.output_amount, c.burned_amount) == (category[::-1].hex(), 10, 7, 3)
    assert c.inputs[0].commitment == '01' and c.outputs[0].commitment == '02'
    assert c.inputs[0].capability == c.outputs[0].capability == 'mutable'
    assert c.outputs[0].index == 1
    assert parser.recipient_output_satoshis == 900
    controller = SimpleNamespace(psbt_parser=parser, token_review=review, token_review_parser=parser,
                                 token_review_acknowledged=set(range(len(review.pages()))))
    overview = views.BCHPSBTOverviewView.__new__(views.BCHPSBTOverviewView)
    overview.controller, overview.is_last = controller, True
    overview.run_screen = Mock(return_value=0)
    overview.run()
    assert overview.run_screen.call_args.kwargs['inputs_amount'] == 900
    assert overview.run_screen.call_args.kwargs['fee_amount'] == 100
    address = views.PSBTAddressDetailsView.__new__(views.PSBTAddressDetailsView)
    address.controller, address.output_num, address.outputs = controller, 0, parser.bch_outputs
    address.category_id = None
    address.run_screen = Mock(return_value=0)
    address.run()
    assert address.run_screen.call_args.kwargs['amount'] == 900
    signer = BitcoinCashSigner(xpriv, parser)
    # Independent construction includes real vout1 and CashToken prefix.
    prevout = txid + bytes(4)
    serialized_outputs = b''.join(sats.to_bytes(8, 'little') + serialize_varint(len(script)) + script for sats, script in outputs)
    preimage = (b'\x02\0\0\0' + double_sha256(prevout) + double_sha256(b'\xff'*4)
                + prevout + token_input + serialize_varint(len(locking)) + locking
                + (1000).to_bytes(8,'little') + b'\xff'*4 + double_sha256(serialized_outputs)
                + bytes(4) + b'\x41\0\0\0')
    sighash = double_sha256(preimage)
    assert signer.create_sighash(parser.tx, 0) == sighash
    signed = signer.signed_psbt()
    parsed = parse_psbt(signed)
    assert parsed['unsigned_tx'] == unsigned
    signature = next(value for k, value in parsed['inputs'][0] if k == b'\x02' + pub)
    assert signature[-1] == 0x41
    r, s = int.from_bytes(signature[:32], 'big'), int.from_bytes(signature[32:64], 'big')
    challenge = int.from_bytes(hashlib.sha256(signature[:32]+pub+sighash).digest(),'big') % ecdsa.SECP256k1.order
    point = s*ecdsa.SECP256k1.generator + (-challenge % ecdsa.SECP256k1.order)*ecdsa.VerifyingKey.from_string(pub,curve=ecdsa.SECP256k1).pubkey.point
    assert point.x() == r
    prime = ecdsa.SECP256k1.curve.p()
    assert pow(point.y(), (prime-1)//2, prime) == 1
    from seedcash.models.encode_qr import UrPsbtQrEncoder
    from seedcash.helpers.ur2.ur_decoder import URDecoder
    encoder, decoder = UrPsbtQrEncoder(psbt=signed), URDecoder()
    for _ in range(encoder.seq_len()):
        assert decoder.receive_part(encoder.next_part())
    restored = PSBTParser(decoder.result_message().cbor)
    assert restored.tx == parser.tx
    assert TokenReview.from_parser(restored) == review
    mutated = bytearray(unsigned)
    # Changing signed output amount must alter sighash; review must change too.
    offset = 4 + 1 + 32 + 4 + 1 + 4 + 1 + 8 + 1 + 5
    mutated[offset] ^= 1
    different = parse_transaction(bytes(mutated))
    different.inputs[0].spent_output = parser.tx.inputs[0].spent_output
    assert signer.create_sighash(different, 0) != sighash
