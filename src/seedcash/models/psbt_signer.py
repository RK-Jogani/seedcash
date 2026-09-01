import hashlib
import ecdsa
from typing import List, Tuple, Optional

from seedcash.models.psbt_parser import (
    PSBTParser,
    parse_transaction,
)
from seedcash.models.bip44 import Bip44

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


# ----------------------------------------------------------------------
# Serialization helpers
# ----------------------------------------------------------------------
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
        raise ValueError("Invalid BIP32 derivation value length")
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
    def __init__(self, xpriv: str, parser: PSBTParser):
        self.parser = parser
        decoded = Bip44.xpriv_decode(xpriv)

        # Store account path for debugging
        self.account_path = Bip44.parse_derivation_path()

        if Bip44.check_depth(decoded["depth"]) is False:
            raise ValueError(f"xpriv depth {decoded['depth']} does not match account_path length {len(self.account_path)}")

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

    def _resolve_utxo_for_hash(self, tx_data: dict, input_index: int) -> Optional[bytes]:
        """Get the full UTXO data for SIGHASH_UTXOS (CashTokens feature)."""
        input_pairs = self.parser.parsed["inputs"][input_index]

        for key, value in input_pairs:
            if key[0] == PSBT_IN_NON_WITNESS_UTXO:
                prev_tx = parse_transaction(value)
                prev_index = int.from_bytes(tx_data["inputs"][input_index]["prev_index"], "little")
                if prev_index < len(prev_tx["outputs"]):
                    out = prev_tx["outputs"][prev_index]
                    return out["value"] + serialize_varint(len(out["script"])) + out["script"]

        # Fallback: use from parser's tx if available
        if input_index < len(self.parser.tx.inputs):
            spent = self.parser.tx.inputs[input_index].spent_output
            if spent:
                return spent.value_satoshis.to_bytes(8, "little") + \
                       serialize_varint(len(spent.full_script)) + spent.full_script

        return None

    def _get_sighash_type(self, input_pairs: List[Tuple[bytes, bytes]]) -> int:
        hash_type = SIGHASH_BCH
        for key, value in input_pairs:
            if key[0] == PSBT_IN_SIGHASH_TYPE:
                ht = int.from_bytes(value, "little")
                if not (ht & SIGHASH_FORKID):
                    raise ValueError(f"Sighash type 0x{ht:02x} missing FORKID bit (required on Bitcoin Cash)")
                hash_type = ht
                break
        return hash_type

    def _create_sighash(self, tx: bytes, input_index: int, script_code: bytes,
                        amount_sats: int, hash_type: int = SIGHASH_BCH) -> bytes:
        """Create BIP-143 sighash for Bitcoin Cash with CashToken support."""
        tx_data = parse_transaction(tx)
        anyone_can_pay = hash_type & SIGHASH_ANYONECANPAY
        mode = hash_type & 0x1F
        utxos_flag = hash_type & SIGHASH_UTXOS

        if input_index >= len(tx_data["inputs"]):
            raise ValueError("input_index out of range")

        # hashPrevouts
        if not anyone_can_pay:
            prevouts = b"".join(txin["prev_txid"] + txin["prev_index"] for txin in tx_data["inputs"])
            hash_prevouts = double_sha256(prevouts)
        else:
            hash_prevouts = b"\x00" * 32

        # hashUTXOs (CashTokens feature)
        if utxos_flag:
            utxo_data = b""
            for i in range(len(tx_data["inputs"])):
                utxo = self._resolve_utxo_for_hash(tx_data, i)
                if utxo is None:
                    raise ValueError(f"Cannot resolve UTXO for input {i} with SIGHASH_UTXOS")
                utxo_data += utxo
            hash_utxos = double_sha256(utxo_data)
        else:
            hash_utxos = b''

        # hashSequence
        if not anyone_can_pay and mode != SIGHASH_NONE:
            sequences = b"".join(txin["sequence"] for txin in tx_data["inputs"])
            hash_sequence = double_sha256(sequences)
        else:
            hash_sequence = b"\x00" * 32

        print(f"hash_utxos: {hash_utxos}")

        # hashOutputs
        if mode == SIGHASH_SINGLE and input_index < len(tx_data["outputs"]):
            out = tx_data["outputs"][input_index]
            hash_outputs = double_sha256(
                out["value"] + serialize_varint(len(out["script"])) + out["script"]
            )
        elif mode == SIGHASH_NONE:
            hash_outputs = b"\x00" * 32
        else:  # SIGHASH_ALL
            out_bytes = b"".join(
                out["value"] + serialize_varint(len(out["script"])) + out["script"]
                for out in tx_data["outputs"]
            )
            hash_outputs = double_sha256(out_bytes)

        txin = tx_data["inputs"][input_index]

        # BIP-143 preimage (no witness data)
        preimage = (
            tx_data["version"]                      # 4 bytes
            + hash_prevouts                         # 32 bytes
            + hash_utxos                            # 32 bytes (CashTokens)
            + hash_sequence                         # 32 bytes
            + txin["prev_txid"]                     # 32 bytes
            + txin["prev_index"]                    # 4 bytes
            + serialize_varint(len(script_code))    # varint
            + script_code                           # variable
            + amount_sats.to_bytes(8, "little")     # 8 bytes
            + txin["sequence"]                      # 4 bytes
            + hash_outputs                          # 32 bytes
            + tx_data["locktime"]                   # 4 bytes
            + hash_type.to_bytes(4, "little")       # 4 bytes
        )
        return double_sha256(preimage)

    def _sign_schnorr(self, private_key: bytes, msg_hash: bytes, public_key: bytes) -> bytes:
        """Sign using Schnorr signature (BCH standard)."""
        d = int.from_bytes(private_key, "big")
        order = ecdsa.SECP256k1.order
        field_prime = ecdsa.SECP256k1.curve.p()

        if d <= 0 or d >= order:
            raise ValueError("invalid private key scalar")
        if len(msg_hash) != 32:
            raise ValueError("msg_hash must be 32 bytes")
        if len(public_key) != 33:
            raise ValueError("public_key must be compressed (33 bytes)")

        k = ecdsa.rfc6979.generate_k(order, d, hashlib.sha256, msg_hash, extra_entropy=b"")
        G = ecdsa.SECP256k1.generator
        R = k * G

        if pow(R.y(), (field_prime - 1) // 2, field_prime) != 1:
            k = order - k
            R = k * G

        r_int = R.x()
        if r_int == 0:
            raise ValueError("invalid nonce: r is zero")

        r_bytes = r_int.to_bytes(32, "big")
        e = int.from_bytes(hashlib.sha256(r_bytes + public_key + msg_hash).digest(), "big") % order
        s = (k + e * d) % order
        if s == 0:
            raise ValueError("invalid signature: s is zero")

        return r_bytes + s.to_bytes(32, "big")

    def _validate_input_for_signing(self, input_pairs: List[Tuple[bytes, bytes]], tx_input, idx: int) -> None:
        """Validate that an input is ready for signing."""
        # Check UTXO data exists (BCH uses NON_WITNESS_UTXO)
        has_utxo = any(key[0] == PSBT_IN_NON_WITNESS_UTXO for key, _ in input_pairs)
        if not has_utxo:
            raise ValueError(f"Input {idx} missing NON_WITNESS_UTXO data")

        if tx_input.spent_output is None:
            raise ValueError(f"Input {idx} has no spent_output")

    def _find_derivation_path(self, input_pairs: List[Tuple[bytes, bytes]]) -> Optional[List[int]]:
        """Find the derivation path for this input."""
        for key, value in input_pairs:
            if key[0] == PSBT_IN_BIP32_DERIVATION:
                fp, path = parse_bip32_derivation_value(value)
                
                if fp == self.master_fingerprint:
                    return path
                
                # Try deriving and checking pubkey
                try:
                    pubkey_in_key = key[1:]
                    _, derived_pub = self._derive_path(path)
                    if derived_pub == pubkey_in_key:
                        return path
                except Exception as e:
                    print(f"  ❌ Derivation error: {e}")
        return None

    # ------------------------------------------------------------------
    # Main signing method
    # ------------------------------------------------------------------
    def signed_psbt(self) -> bytearray:
        """Sign the PSBT with the wallet's private keys."""
        parsed = self.parser.parsed
        tx_bytes = parsed["unsigned_tx"]
        if tx_bytes is None:
            raise ValueError("No unsigned transaction in PSBT")
    
        input_maps = [pairs.copy() for pairs in parsed["inputs"]]
        input_starts = self.parser.parsed["input_starts"]
        input_ends = self.parser.parsed["input_ends"]
    
        # Collect inputs to sign
        inputs_to_sign = []
        for idx, tx_input in enumerate(self.parser.tx.inputs):
            if tx_input.spent_output is None:
                continue
    
            input_pairs = input_maps[idx]
    
            try:
                self._validate_input_for_signing(input_pairs, tx_input, idx)
            except ValueError as e:
                print(f"Input {idx} validation failed: {e}")
                continue
    
            derivation_path = self._find_derivation_path(input_pairs)
            if derivation_path is None:
                print(f"Input {idx}: no matching derivation path")
                continue
    
            priv, pub = self._derive_path(derivation_path)
            partial_key = bytes([PSBT_IN_PARTIAL_SIG]) + pub
    
            if any(k == partial_key for k, _ in input_pairs):
                print(f"Input {idx}: already signed by this pubkey")
                continue
    
            inputs_to_sign.append((idx, tx_input, input_pairs, derivation_path, priv, pub, partial_key))
    
        if not inputs_to_sign:
            print("No inputs to sign")
            # Return the original PSBT
            return bytearray(self.parser.psbt_bytes)
    
        # Sign each input
        for idx, tx_input, input_pairs, derivation_path, priv, pub, partial_key in inputs_to_sign:
            script_code = None
            for key, value in input_pairs:
                if key[0] == PSBT_IN_REDEEM_SCRIPT:
                    script_code = value
                    break
            if script_code is None:
                script_code = tx_input.spent_output.full_script
    
            hash_type = self._get_sighash_type(input_pairs)
            amount = tx_input.spent_output.value_satoshis
    
            sighash = self._create_sighash(tx_bytes, idx, script_code, amount, hash_type)
            print(f"Hash Type {hash_type}")
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
        psbt = bytearray(self.parser.psbt_bytes[:input_starts[0]])
        for pairs in input_maps:
            psbt += _serialize_keypairs(pairs) + b"\x00"
        psbt += self.parser.psbt_bytes[input_ends[0]:]
        return  psbt

