import hashlib
import hmac
from typing import List, Tuple
from seedcash.models.settings_definition import SettingsConstants as SC 
from base58 import b58decode, b58encode
from ecdsa import SECP256k1, SigningKey, VerifyingKey

class Bip44:

    @staticmethod
    def sha256(data):
        return hashlib.sha256(data).digest()

    @staticmethod
    def double_sha256(data):
        """Bitcoin's double SHA256 (SHA256d)"""
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()

    @staticmethod
    def xpriv_encode(
        depth, father_fingerprint, child_index, account_chain_code, account_key
    ):
        version = b"\x04\x88\xad\xe4"  # xpriv
        data = (
            version
            + depth
            + father_fingerprint
            + child_index
            + account_chain_code
            + b"\x00"
            + account_key
        )
        checksum = Bip44.double_sha256(data)[:4]
        return b58encode(data + checksum).decode("utf-8")

    @staticmethod
    def xpriv_decode(xpriv):
        decoded = b58decode(xpriv)
        if len(decoded) != 82:
            raise ValueError("not an extended private key")
        
        payload = decoded[:-4]
        checksum = decoded[-4:]
        if Bip44.double_sha256(payload)[:4] != checksum:
            raise ValueError("invalid xpriv checksum")
        
        key_data = payload[45:78]
        if key_data[0] != 0x00:
            raise ValueError("extended key is not private")
        
        return {
            "depth": payload[4],
            "fingerprint": payload[5:9],
            "child_number": int.from_bytes(payload[9:13], 'big'),
            "chain_code": payload[13:45],
            "private_key": key_data[1:],
        }

    @staticmethod
    def xpub_encode(
        depth, father_fingerprint, child_index, account_chain_code, account_public_key
    ):
        version = b"\x04\x88\xb2\x1e"  # xpub
        data = (
            version
            + depth
            + father_fingerprint
            + child_index
            + account_chain_code
            + account_public_key
        )
        checksum = Bip44.double_sha256(data)[:4]
        return b58encode(data + checksum).decode("utf-8")

    @staticmethod
    def xpub_decode(xpub):
        """Decode xpub from base58 to byte components"""
        xpub_bytes = b58decode(xpub)
        version = xpub_bytes[:4]
        depth = xpub_bytes[4:5]
        fingerprint = xpub_bytes[5:9]
        child_number = xpub_bytes[9:13]
        chain_code = xpub_bytes[13:45]
        public_key = xpub_bytes[45:-4]
        return version, depth, fingerprint, child_number, chain_code, public_key

    @staticmethod
    def hmac_sha512(key, data):
        return hmac.new(key, data, hashlib.sha512).digest()

    @staticmethod
    def private_to_public(private_key_bytes: bytes) -> bytes:
        """Convert a private key (32 bytes) to compressed public key (33 bytes)."""
        sk = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
        vk = sk.verifying_key
        return vk.to_string("compressed")

    @staticmethod
    def derive_child_key(
        parent_key: bytes,
        parent_chain_code: bytes,
        index: int,
        is_private: bool = True,
        hardened: bool = False
    ) -> Tuple[bytes, bytes]:
        """
        BIP32 child key derivation for both private and public keys.
        
        Args:
            parent_key: 32-byte private key OR 33-byte compressed public key
            parent_chain_code: 32-byte chain code
            index: Child index (0-0x7fffffff for normal, 0x80000000+ for hardened)
            is_private: True for private derivation, False for public
            hardened: True for hardened derivation (sets the hardened bit)
        
        Returns:
            (child_key, child_chain_code)
            - Private: child_key is 32 bytes
            - Public: child_key is 33 bytes (compressed)
        
        Raises:
            ValueError: On invalid inputs or cryptographic failure
        """
        curve = SECP256k1.curve
        generator = SECP256k1.generator
        order = SECP256k1.order
        
        # Apply hardened bit if requested
        if hardened:
            index |= 0x80000000
        
        is_hardened = index & 0x80000000 != 0
        
        # Validate inputs and prepare HMAC data
        if is_private:
            if len(parent_key) != 32:
                raise ValueError("Private key must be 32 bytes")
            
            # BIP32: For hardened, use 0x00 + private_key
            # For non-hardened, use public_key (BIP32 specification)
            if is_hardened:
                data = b"\x00" + parent_key + index.to_bytes(4, "big")
            else:
                # Non-hardened: use public key
                parent_pub = Bip44.private_to_public(parent_key)
                data = parent_pub + index.to_bytes(4, "big")
        else:
            # Public key derivation
            if is_hardened:
                raise ValueError("Cannot derive hardened child from public key")
            if len(parent_key) != 33:
                raise ValueError("Public key must be 33 bytes (compressed)")
            data = parent_key + index.to_bytes(4, "big")
        
        # HMAC-SHA512
        I = hmac.new(parent_chain_code, data, hashlib.sha512).digest()
        IL, IR = I[:32], I[32:]
        
        IL_int = int.from_bytes(IL, "big")
        if IL_int >= order:
            raise ValueError("IL >= curve order (rare, try next index)")
        
        # Derive child key based on type
        if is_private:
            # Private key derivation: child_key = (IL + parent_key) % order
            parent_int = int.from_bytes(parent_key, "big")
            child_int = (IL_int + parent_int) % order
            
            if child_int == 0:
                raise ValueError("Derived private key is zero (try next index)")
            
            child_key = child_int.to_bytes(32, "big")
        else:
            # Public key derivation: child_point = IL * G + parent_point
            parent_public_key = VerifyingKey.from_string(parent_key, curve=SECP256k1)
            child_point = (generator * IL_int) + parent_public_key.pubkey.point
            
            if child_point == curve.infinity():
                raise ValueError("Derived point is at infinity (try next index)")
            
            child_key = VerifyingKey.from_public_point(
                child_point, curve=SECP256k1
            ).to_string("compressed")
        
        return child_key, IR

    @staticmethod
    def derive_hardened_child(
        parent_key: bytes,
        parent_chain_code: bytes,
        index: int,
        is_private: bool = True
    ) -> Tuple[bytes, bytes]:
        """
        Convenience method for hardened derivation.
        Equivalent to derive_child_key(..., hardened=True)
        """
        return Bip44.derive_child_key(
            parent_key=parent_key,
            parent_chain_code=parent_chain_code,
            index=index,
            is_private=is_private,
            hardened=True
        )

    @staticmethod
    def derive_normal_child(
        parent_key: bytes,
        parent_chain_code: bytes,
        index: int,
        is_private: bool = True
    ) -> Tuple[bytes, bytes]:
        """
        Convenience method for normal (non-hardened) derivation.
        Equivalent to derive_child_key(..., hardened=False)
        """
        return Bip44.derive_child_key(
            parent_key=parent_key,
            parent_chain_code=parent_chain_code,
            index=index,
            is_private=is_private,
            hardened=False
        )

    @staticmethod
    def fingerprint_hex(account_key):
        """Given a private key, return the master fingerprint in hex"""
        sk = SigningKey.from_string(account_key, curve=SECP256k1)
        vk = sk.verifying_key
        public_key_compressed = vk.to_string("compressed")
        
        sha256_hash = hashlib.sha256(public_key_compressed).digest()
        ripemd160 = hashlib.new("ripemd160")
        ripemd160.update(sha256_hash)
        fingerprint = ripemd160.digest()[:4]
        return fingerprint.hex()

    @staticmethod
    def public_master_key_compressed_generaitor(private_master_key_bytes):
        """Convert private key to compressed public key"""
        sk = SigningKey.from_string(private_master_key_bytes, curve=SECP256k1)
        vk = sk.verifying_key
        public_key_compressed = vk.to_string("compressed")
        return public_key_compressed

    @staticmethod
    def fingerprint_bytes(compressed_master_public_key_bytes):
        """Given compressed public key, return the fingerprint in bytes"""
        sha256_hash = hashlib.sha256(compressed_master_public_key_bytes).digest()
        ripemd160 = hashlib.new("ripemd160")
        ripemd160.update(sha256_hash)
        fingerprint = ripemd160.digest()[:4]
        return fingerprint

    @staticmethod
    def get_wallet_data(private_master_key, private_master_code):
        """Generate wallet data from master private key and chain code"""
        wallet_fingerprint = Bip44.fingerprint_hex(private_master_key)
        
        # Derive purpose: 44' (hardened)
        purpose_key, purpose_chain_code = Bip44.derive_child_key(
            parent_key=private_master_key,
            parent_chain_code=private_master_code,
            index=44,
            is_private=True,
            hardened=True  # 44'
        )
        
        # Derive coin type: 145' (hardened)
        coin_type_key, coin_type_chain_code = Bip44.derive_child_key(
            parent_key=purpose_key,
            parent_chain_code=purpose_chain_code,
            index=145,
            is_private=True,
            hardened=True  # 145'
        )
        
        # Derive account: 0' (hardened)
        account_key, account_chain_code = Bip44.derive_child_key(
            parent_key=coin_type_key,
            parent_chain_code=coin_type_chain_code,
            index=0,
            is_private=True,
            hardened=True  # 0'
        )
        account_public_key = Bip44.public_master_key_compressed_generaitor(account_key)
        
        # Depth
        depth = 3
        depth = depth.to_bytes(1, byteorder="big")
        
        # Fingerprint of parent (coin_type key)
        father_account_publickey = Bip44.public_master_key_compressed_generaitor(
            coin_type_key
        )
        father_fingerprint = Bip44.fingerprint_bytes(father_account_publickey)
        
        # Child index
        child_index = 0 | 0x80000000
        child_index = child_index.to_bytes(4, byteorder="big")
        
        xpriv = Bip44.xpriv_encode(
            depth,
            father_fingerprint,
            child_index,
            account_chain_code,
            account_key,
        )
        
        xpub = Bip44.xpub_encode(
            depth,
            father_fingerprint,
            child_index,
            account_chain_code,
            account_public_key,
        )
        
        return xpriv, xpub, wallet_fingerprint

    # Cashaddr address generation
    @staticmethod
    def xpub_to_cashtoken_address(xpub, address_index):
        """Convert xpub to CashToken address (z-prefixed)"""
        addr = Bip44.xpub_to_cashaddr_address(xpub, address_index)
        return addr.replace("q", "z", 1)

    @staticmethod
    def convert_bits(data, from_bits, to_bits, pad=True):
        acc = 0
        bits = 0
        ret = []
        maxv = (1 << to_bits) - 1
        for value in data:
            acc = (acc << from_bits) | value
            bits += from_bits
            while bits >= to_bits:
                bits -= to_bits
                ret.append((acc >> bits) & maxv)
        if pad and bits:
            ret.append((acc << (to_bits - bits)) & maxv)
        return ret

    @staticmethod
    def polymod(values):
        c = 1
        for d in values:
            c0 = c >> 35
            c = ((c & 0x07FFFFFFFF) << 5) ^ d
            if c0 & 0x01:
                c ^= 0x98F2BC8E61
            if c0 & 0x02:
                c ^= 0x79B76D99E2
            if c0 & 0x04:
                c ^= 0xF33E5FB3C4
            if c0 & 0x08:
                c ^= 0xAE2EABE2A8
            if c0 & 0x10:
                c ^= 0x1E4F43E470
        return c ^ 1

    @staticmethod
    def create_checksum(prefix, payload):
        values = [ord(x) & 0x1F for x in prefix] + [0] + payload
        polymod_result = Bip44.polymod(values + [0, 0, 0, 0, 0, 0, 0, 0])
        return [(polymod_result >> (5 * (7 - i))) & 0x1F for i in range(8)]

    @staticmethod
    def encode_base32(data):
        CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        return "".join([CHARSET[d] for d in data])

    @staticmethod
    def hash160(pubkey):
        sha256_hash = hashlib.sha256(pubkey).digest()
        ripemd160_hash = hashlib.new("ripemd160", sha256_hash).digest()
        return ripemd160_hash

    @staticmethod
    def public_key_to_cashaddr_address(pubkey):
        version_byte = 0x00  # P2PKH
        payload = bytes([version_byte]) + Bip44.hash160(pubkey)
        payload_5bit = Bip44.convert_bits(payload, 8, 5)
        checksum = Bip44.create_checksum("bitcoincash", payload_5bit)
        address = "bitcoincash:" + Bip44.encode_base32(payload_5bit + checksum)
        return address

    @staticmethod
    def hash160_to_cashaddr(hash160: bytes, version_byte: int = 0x00) -> str:
        """Convert a 20-byte HASH160 to a cashaddr string.
        - version_byte: 0x00 for P2PKH (q...), 0x08 for P2SH (p...).
        """
        if len(hash160) != 20:
            raise ValueError("hash160 must be 20 bytes")
        payload = bytes([version_byte]) + hash160
        payload_5bit = Bip44.convert_bits(payload, 8, 5)
        checksum = Bip44.create_checksum("bitcoincash", payload_5bit)
        return "bitcoincash:" + Bip44.encode_base32(payload_5bit + checksum)

    @staticmethod
    def xpub_to_cashaddr_address(xpub, address_index):
        """Convert xpub to cashaddr address for a given index"""
        (
            version,
            depth,
            fingerprint,
            child_number,
            chain_code_chain,
            public_key_chain,
        ) = Bip44.xpub_decode(xpub)
        
        # Derive m/44'/145'/0'/0 (non-hardened public)
        child_public_chain, child_chain_chain = Bip44.derive_child_key(
            parent_key=public_key_chain,
            parent_chain_code=chain_code_chain,
            index=0,
            is_private=False,
            hardened=False
        )
        
        # Derive m/44'/145'/0'/0/address_index (non-hardened public)
        child_public_address_index, child_chain_address_index = Bip44.derive_child_key(
            parent_key=child_public_chain,
            parent_chain_code=child_chain_chain,
            index=address_index,
            is_private=False,
            hardened=False
        )
        
        address = Bip44.public_key_to_cashaddr_address(child_public_address_index)
        return address

    @staticmethod
    def parse_derivation_path(path: str = SC.BCH_ACCOUNT_PATH) -> List[int]:
        """Parse a BIP32 derivation path string to a list of integers."""
        if not path:
            return []
        path = path.strip()
        if path in ("m", "M"):
            return []
        if path.startswith("m/") or path.startswith("M/"):
            path = path[2:]
    
        components = []
        for item in path.split("/"):
            item = item.strip()
            if not item:
                continue
            hardened = item[-1] in ("'", "h", "H")
            if hardened:
                item = item[:-1]
            index = int(item)
            if hardened:
                index |= 0x80000000
            components.append(index)
        return components

    @staticmethod
    def check_depth(depth: int) -> bool:
        """Check if the depth is valid for the BCH_ACCOUNT_PATH."""
        account_path = Bip44.parse_derivation_path()
        return depth == len(account_path)