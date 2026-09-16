# NEW
import hashlib
import ecdsa
from typing import List, Tuple, Optional

from seedcash.models.psbt_parser import (
    PSBTParser,
    ParseTransactionResult,
    parse_psbt,
    parse_transaction,
)
from seedcash.models.bip44 import Bip44

import logging
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# PSBT key constants (BIP‑174)
# ----------------------------------------------------------------------
PSBT_GLOBAL_UNSIGNED_TX      = 0x00
PSBT_GLOBAL_INPUT_COUNT      = 0x04
PSBT_GLOBAL_OUTPUT_COUNT     = 0x05
PSBT_GLOBAL_VERSION          = 0xFB
PSBT_GLOBAL_PROPRIETARY      = 0xFC

PSBT_IN_NON_WITNESS_UTXO     = 0x00
PSBT_IN_SIGHASH_TYPE         = 0x03
PSBT_IN_PARTIAL_SIG          = 0x02
PSBT_IN_REDEEM_SCRIPT        = 0x04
PSBT_IN_BIP32_DERIVATION     = 0x06

PSBT_OUT_AMOUNT              = 0x00
PSBT_OUT_SCRIPT              = 0x01
PSBT_OUT_BIP32_DERIVATION    = 0x02

# Bitcoin Cash sighash flags
SIGHASH_ALL                  = 0x01
SIGHASH_NONE                 = 0x02
SIGHASH_SINGLE               = 0x03
SIGHASH_ANYONECANPAY         = 0x80
SIGHASH_FORKID               = 0x40
SIGHASH_UTXOS                = 0x20

SIGHASH_BCH = SIGHASH_ALL | SIGHASH_FORKID

ALLOWED_SIGHASH = frozenset({
    SIGHASH_ALL | SIGHASH_FORKID,
    SIGHASH_ALL | SIGHASH_FORKID | SIGHASH_UTXOS,
})


# ----------------------------------------------------------------------
# Serialization helpers
# ----------------------------------------------------------------------

class BCHSignerExpectation(Exception):
    """Raised when the PSBT signer encounters an unexpected condition."""
    pass

def serialize_varint(n: int) -> bytes:
    if n < 0xfd:
        return n.to_bytes(1, "little")
    elif n <= 0xffff:
        return b"\xfd" + n.to_bytes(2, "little")
    elif n <= 0xffffffff:
        return b"\xfe" + n.to_bytes(4, "little")
    else:
        return b"\xff" + n.to_bytes(8, "little")


def _serialize_keypairs(pairs: List[Tuple[bytes, bytes]]) -> bytes:
    out = b""
    for key, value in pairs:
        out += serialize_varint(len(key)) + key + serialize_varint(len(value)) + value
    return out

def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


# ----------------------------------------------------------------------
# BIP32 derivation helpers
# ----------------------------------------------------------------------
def parse_bip32_derivation_value(value: bytes) -> Tuple[bytes, List[int]]:
    if len(value) < 4 or (len(value) - 4) % 4 != 0:
        raise BCHSignerExpectation("Invalid BIP32 derivation value length")
    master_fingerprint = value[:4]
    path = [int.from_bytes(value[i:i+4], 'little') for i in range(4, len(value), 4)]
    return master_fingerprint, path





def path_to_string(path: List[int]) -> str:
    """Convert BIP32 path list to readable string."""
    result = "m"
    for idx in path:
        if idx & 0x80000000:
            result += f"/{idx & 0x7fffffff}'"
        else:
            result += f"/{idx}"
    return result


# ----------------------------------------------------------------------
# Bitcoin Cash Signer
# ----------------------------------------------------------------------
class BitcoinCashSigner:
    def __init__(self, xpriv: bytearray, parser: PSBTParser):
        self.parser = parser
        decoded = Bip44.xpriv_decode(xpriv)

        # Store account path for debugging
        self.account_path = Bip44.parse_derivation_path()

        if Bip44.check_depth(decoded["depth"]) is False:
            raise BCHSignerExpectation(f"xpriv depth {decoded['depth']} does not match account_path length {len(self.account_path)}")

        self.depth = decoded["depth"]
        self.private_key = decoded["private_key"]
        self.chain_code = decoded["chain_code"]
        self.master_fingerprint = decoded["fingerprint"]
        self._key_cache = {}

    def _derive_path(self, path: List[int]) -> Tuple[bytes, bytes]:
        """
        Derive the private key and public key for a given BIP32 path.
        Uses Bip44.derive_child_key for all derivations.
        """
        cache_key = tuple(path)
        if cache_key in self._key_cache:
            return self._key_cache[cache_key]

        priv, chain = self.private_key, self.chain_code
        
        # Start deriving from the wallet's depth
        start_idx = self.depth if len(path) > self.depth else 0
        
        for idx in path[start_idx:]:
            # Determine if this is hardened
            is_hardened = idx & 0x80000000 != 0
            
            # Use the unified Bip44.derive_child_key
            priv, chain = Bip44.derive_child_key(
                parent_key=priv,
                parent_chain_code=chain,
                index=idx,
                is_private=True,
                hardened=is_hardened
            )
            
        pub = Bip44.private_to_public(priv)

        self._key_cache[cache_key] = (priv, pub)
        return priv, pub

    def _get_sighash_type(self, input_pairs: List[Tuple[bytes, bytes]]) -> int:
        hash_type = SIGHASH_BCH
        for key, value in input_pairs:
            if key[0] == PSBT_IN_SIGHASH_TYPE:
                hash_type = int.from_bytes(value, "little")
                break
        if hash_type not in ALLOWED_SIGHASH:
            raise BCHSignerExpectation(
                f"refusing to sign with sighash 0x{hash_type:02x}; "
                f"only ALL|FORKID (optionally |UTXOS) is supported"
            )
        return hash_type

    def create_sighash(self, tx_data: ParseTransactionResult, input_index: int, hash_type: int = SIGHASH_BCH, script_code: bytes = None) -> bytes:
        """Create BIP-143 sighash for Bitcoin Cash with CashToken support."""
        if hash_type not in ALLOWED_SIGHASH:
            raise BCHSignerExpectation(
                f"refusing to create sighash 0x{hash_type:02x}; "
                f"only ALL|FORKID (optionally |UTXOS) is supported"
            )
        anyone_can_pay = hash_type & SIGHASH_ANYONECANPAY
        mode = hash_type & 0x1F
        utxos_flag = hash_type & SIGHASH_UTXOS

        
        if not anyone_can_pay:
            prevouts = b"".join(
                txin.prev_txid 
                + txin.prev_index.to_bytes(4, "little") 
                for txin in tx_data.inputs)
            hash_prevouts = double_sha256(prevouts)
            if mode != SIGHASH_NONE:
                sequences = b"".join(txin.sequence.to_bytes(4, "little") for txin in tx_data.inputs)
                hash_sequence = double_sha256(sequences)
            else:
                hash_sequence = b"\x00" * 32
        else:
            hash_prevouts = b"\x00" * 32
            hash_sequence = b"\x00" * 32

        # hashUTXOs (CashTokens feature)
        if utxos_flag:
            utxo_data = b''
            for txin in tx_data.inputs:
                spent = txin.spent_output
                if spent is None:
                    raise BCHSignerExpectation("SIGHASH_UTXOS requires every input UTXO to be resolved")
                utxo_data += (
                    spent.value_satoshis.to_bytes(8, "little")
                    + serialize_varint(len(spent.full_script))
                    + spent.full_script
                )
            hash_utxos = double_sha256(utxo_data)  
        else:
            hash_utxos = b''


        # hashOutputs
        if mode == SIGHASH_NONE:
            hash_outputs = b"\x00" * 32
        elif mode == SIGHASH_SINGLE and input_index < len(tx_data.outputs):
            out = tx_data.outputs[input_index]
            hash_outputs = double_sha256(
                out.value_satoshis.to_bytes(8, "little") 
                + serialize_varint(len(out.full_script)) 
                + out.full_script
            )
        else:
            out_bytes = b"".join(
                out.value_satoshis.to_bytes(8, "little") 
                + serialize_varint(len(out.full_script)) 
                + out.full_script
                for out in tx_data.outputs
            )
            hash_outputs = double_sha256(out_bytes)

        txin = tx_data.inputs[input_index]
        token_prefix = txin.spent_output.token.prefix if txin.spent_output.token else b''
        if script_code is None:
            script_code = txin.spent_output.script_pubkey

        # BIP-143 preimage (no witness data)
        preimage = (
            tx_data.version                         # 4 bytes
            + hash_prevouts                         # 32 bytes
            + hash_utxos                            # 32 bytes (CashTokens)
            + hash_sequence                         # 32 bytes
            + txin.prev_txid                        # 32 bytes
            + txin.prev_index.to_bytes(4, "little") # 4 bytes
            + token_prefix                           # variable (CashTokens)
            + serialize_varint(len(script_code))    # varint
            + script_code                           # variable
            + txin.spent_output.value_satoshis.to_bytes(8, "little")     # 8 bytes
            + txin.sequence.to_bytes(4, "little")   # 4 bytes
            + hash_outputs                          # 32 bytes
            + tx_data.locktime                      # 4 bytes
            + hash_type.to_bytes(4, "little")       # 4 bytes
        )
        return double_sha256(preimage)

    def _sign_schnorr(self, private_key: bytes, msg_hash: bytes, public_key: bytes) -> bytes:
        """Sign using Schnorr signature (BCH standard)."""
        d = int.from_bytes(private_key, "big")
        order = ecdsa.SECP256k1.order
        field_prime = ecdsa.SECP256k1.curve.p()

        if d <= 0 or d >= order:
            raise BCHSignerExpectation("invalid private key scalar")
        if len(msg_hash) != 32:
            raise BCHSignerExpectation("msg_hash must be 32 bytes")
        if len(public_key) != 33:
            raise BCHSignerExpectation("public_key must be compressed (33 bytes)")

        k = ecdsa.rfc6979.generate_k(order, d, hashlib.sha256, msg_hash, extra_entropy=b"Schnorr+SHA256 ")
        G = ecdsa.SECP256k1.generator
        R = k * G

        if pow(R.y(), (field_prime - 1) // 2, field_prime) != 1:
            k = order - k
            R = k * G

        r_int = R.x()
        if r_int == 0:
            raise BCHSignerExpectation("invalid nonce: r is zero")

        r_bytes = r_int.to_bytes(32, "big")
        e = int.from_bytes(hashlib.sha256(r_bytes + public_key + msg_hash).digest(), "big") % order
        s = (k + e * d) % order
        if s == 0:
            raise BCHSignerExpectation("invalid signature: s is zero")

        return r_bytes + s.to_bytes(32, "big")

    def find_derivation_path(self, input_pairs: List[Tuple[bytes, bytes]]) -> Optional[List[int]]:
        """Find the derivation path for this input."""
        for key, value in input_pairs:
            if key[0] == PSBT_IN_BIP32_DERIVATION:
                fp, path = parse_bip32_derivation_value(value)
                
                if fp == self.master_fingerprint:
                    return path
                
                try:
                    pubkey_in_key = key[1:]
                    _, derived_pub = self._derive_path(path)
                    if derived_pub == pubkey_in_key:
                        return path
                except BCHSignerExpectation as e:
                    logger.debug(f"Error deriving path {path}: {e}")
                    continue
        return None

    def validate_signed_psbt(self, psbt: bytes):
        """Validate the signed PSBT against the original transaction."""
        reparsed = parse_psbt(bytes(psbt))

        if reparsed["unsigned_tx"] != self.parser.parsed["unsigned_tx"]:
            raise BCHSignerExpectation("signed PSBT changed the unsigned transaction under review")

        reviewed_tx = parse_transaction(reparsed["unsigned_tx"])
        if len(reviewed_tx.outputs) != len(self.parser.tx.outputs):
            raise BCHSignerExpectation("signed PSBT output count differs from the reviewed transaction")
        for reviewed_output, reparsed_output in zip(self.parser.tx.outputs, reviewed_tx.outputs):
            if (reviewed_output.value_satoshis != reparsed_output.value_satoshis
                    or reviewed_output.full_script != reparsed_output.full_script):
                raise BCHSignerExpectation("signed PSBT output differs from the reviewed value or script")

    def clear(self):
        self.private_key = None
        self.chain_code = None
        self._key_cache.clear()

    # ------------------------------------------------------------------
    # Main signing method
    # ------------------------------------------------------------------
    def signed_psbt(self) -> bytearray:
        """Sign the PSBT with the wallet's private keys."""
        
        if self.parser.tx is None:
            raise BCHSignerExpectation("No unsigned transaction in PSBT")
    
        input_maps = self.parser.parsed["inputs"]
        input_starts = self.parser.parsed["input_starts"]
        input_ends = self.parser.parsed["input_ends"]
    
        # Collect inputs to sign
        inputs_to_sign = []
        for idx, tx_input in enumerate(self.parser.tx.inputs):
            if tx_input.spent_output is None:
                continue

            derivation_path = self.find_derivation_path(input_maps[idx])

            if derivation_path is None:
                continue
    
            priv, pub = self._derive_path(derivation_path)
            partial_key = bytes([PSBT_IN_PARTIAL_SIG]) + pub

            if any(k == partial_key for k, _ in input_maps[idx]):
                continue
    
            inputs_to_sign.append((idx, tx_input, input_maps[idx], priv, pub, partial_key))
    
        if not inputs_to_sign:
            raise BCHSignerExpectation("PSBT does not contain any inputs that can be signed with the provided wallet keys")
    
        # Sign each input
        for idx, tx_input, input_pairs, priv, pub, partial_key in inputs_to_sign:
            hash_type = self._get_sighash_type(input_pairs)
            script_code = None
            for key, value in input_pairs:
                if key[0] == PSBT_IN_REDEEM_SCRIPT:
                    script_code = value
                    break

            sighash = self.create_sighash(self.parser.tx, idx, hash_type, script_code=script_code)
            sig = self._sign_schnorr(priv, sighash, pub) + bytes([hash_type & 0xFF])
    
            updated_pairs = []
                    
            # First, add 0x10 if present
            for key, value in input_pairs:
                if key[0] == 0x10:
                    updated_pairs.append((key, value))
                    break
            
            # Then add 0x00 if present
            for key, value in input_pairs:
                if key[0] == 0x00:
                    updated_pairs.append((key, value))
                    break
            
            # Then add all existing 0x02 signatures
            for key, value in input_pairs:
                if key[0] == 0x02:
                    updated_pairs.append((key, value))
            
            # Then add your new signature
            updated_pairs.append((partial_key, sig))
            
            # Finally add everything else (0x04, 0x06, 0x07, 0x0e, 0x0f)
            for key, value in input_pairs:
                if key[0] not in (0x10, 0x00, 0x02):
                    updated_pairs.append((key, value))
            for key, value in updated_pairs:
                if key[0] == 0x04:
                    break

            input_maps[idx] = updated_pairs

        # Rebuild PSBT
        psbt = bytearray(self.parser.psbt_bytes[:input_starts])
        for pairs in input_maps:
            psbt += _serialize_keypairs(pairs) + b"\x00"
        psbt += self.parser.psbt_bytes[input_ends:]

        try:
            self.validate_signed_psbt(psbt)
            return psbt
        except BCHSignerExpectation as e:
            logger.error(f"Signed PSBT validation failed: {e}")
            raise
        finally:
            self.clear()