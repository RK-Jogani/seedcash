import hashlib
import hmac
import os
from base58 import b58decode, b58encode
from ecdsa import SECP256k1, SigningKey, VerifyingKey
from ecdsa.util import string_to_number, number_to_string


class Bip44:

    @staticmethod
    def sha256(data):
        return hashlib.sha256(data).digest()

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
        checksum = Bip44.sha256(Bip44.sha256(data))[:4]

        return b58encode(data + checksum).decode("utf-8")

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
        checksum = Bip44.sha256(Bip44.sha256(data))[:4]

        return b58encode(data + checksum).decode("utf-8")

    @staticmethod
    def xpub_decode(xpub):
        """De xpub en base 58 a components en bytes"""

        xpub_bytes = b58decode(xpub)

        version = xpub_bytes[:4]
        depth = xpub_bytes[4:5]
        fingerprint = xpub_bytes[5:9]
        child_number = xpub_bytes[9:13]
        chain_code = xpub_bytes[13:45]
        public_key = xpub_bytes[45:-4]

        return version, depth, fingerprint, child_number, chain_code, public_key

    @staticmethod
    def derive_public_child_key(parent_public_key_bytes, parent_chain_code, index):
        """Variables parent en bytes, index en int"""

        curve = SECP256k1.curve
        generator = SECP256k1.generator
        order = generator.order()

        data = parent_public_key_bytes + index.to_bytes(4, "big")
        I = hmac.new(parent_chain_code, data, hashlib.sha512).digest()
        IL, IR = I[:32], I[32:]

        IL_int = int.from_bytes(IL, "big")  # Convertir IL a un enter
        if IL_int >= order:
            raise ValueError()

        parent_public_key = VerifyingKey.from_string(
            parent_public_key_bytes, curve=SECP256k1
        )  # Obtenir el punt públic de la clau parent

        child_point = (
            generator * IL_int + parent_public_key.pubkey.point
        )  # Calcular el nou punt de la corba (IL * G + ParentPublicKey)

        child_public_key_bytes = VerifyingKey.from_public_point(
            child_point, curve=SECP256k1
        ).to_string(
            "compressed"
        )  # Convertir el punt resultant a bytes utilitzant VerifyingKey

        child_chain_code = IR

        return child_public_key_bytes, child_chain_code

    # Legacy address generator
    @staticmethod
    def public_key_to_legacy_address(public_key_bytes):

        # SHA-256 hash
        sha256 = hashlib.sha256(public_key_bytes).digest()

        # RIPEMD-160 hash
        ripemd160 = hashlib.new("ripemd160")
        ripemd160.update(sha256)
        ripemd160_hash = ripemd160.digest()

        # Add version byte (0x00 for Bitcoin addresses)
        versioned_hash = b"\x00" + ripemd160_hash

        # Compute checksum
        checksum = hashlib.sha256(hashlib.sha256(versioned_hash).digest()).digest()[:4]

        # Create final address
        address_bytes = versioned_hash + checksum
        bitcoin_address = b58encode(address_bytes).decode("utf-8")

        return bitcoin_address

    @staticmethod
    def xpub_to_legacy_address(xpub, address_index):

        (
            version,
            depth,
            fingerprint,
            child_number,
            chain_code_chain,
            public_key_chain,
        ) = Bip44.xpub_decode(
            xpub
        )  # m/44'/145'/0'

        child_public_chain, child_chain_chain = Bip44.derive_public_child_key(
            public_key_chain, chain_code_chain, 0
        )  # m/44'/145'/0'/0
        child_public_address_index, child_chain_address_index = (
            Bip44.derive_public_child_key(
                child_public_chain, child_chain_chain, address_index
            )
        )  # m/44'/0'/0'/0/0
        address = Bip44.public_key_to_legacy_address(child_public_address_index)

        return address

    @staticmethod
    def hmac_sha512(key, data):
        return hmac.new(key, data, hashlib.sha512).digest()

    @staticmethod
    def child_key_hardened(parent_key, parent_chain_code, index, hardened=False):
        curve_order = SECP256k1.order
        if hardened:
            index |= 0x80000000
        index_bytes = index.to_bytes(4, "big")
        data = b"\x00" + parent_key + index_bytes
        I = Bip44.hmac_sha512(parent_chain_code, data)

        Il = I[:32]
        chain_code = I[32:]

        number_Il = string_to_number(Il)
        number_parent = string_to_number(parent_key)
        number_derived = (number_Il + number_parent) % curve_order

        derivet_key = number_to_string(number_derived, curve_order)

        return derivet_key, chain_code

    @staticmethod
    def fingerprint_hex(account_key):
        """Donada una compressed_master_public_key_bytes retorna un master fingerprint en hexadecimal"""

        sk = SigningKey.from_string(account_key, curve=SECP256k1)
        vk = sk.verifying_key
        public_key_compressed = vk.to_string(
            "compressed"
        )  # clau publica mestre comprimida en hexadecimal

        sha256_hash = hashlib.sha256(public_key_compressed).digest()
        ripemd160 = hashlib.new("ripemd160")
        ripemd160.update(sha256_hash)
        fingerprint = ripemd160.digest()[:4]
        return fingerprint.hex()

    @staticmethod
    def public_master_key_compressed_generaitor(private_master_key_bytes):
        """Partin duna clau privada mestre en format bytes,
        retorna una clau publica en format comprimida en bytes"""

        sk = SigningKey.from_string(private_master_key_bytes, curve=SECP256k1)
        vk = sk.verifying_key
        public_key_compressed = vk.to_string("compressed")
        return public_key_compressed

    @staticmethod
    def fingerprint_bytes(compressed_master_public_key_bytes):
        """Donada una compressed_master_public_key_bytes retorna un master fingerprint en hexadecimal"""

        sha256_hash = hashlib.sha256(compressed_master_public_key_bytes).digest()
        ripemd160 = hashlib.new("ripemd160")
        ripemd160.update(sha256_hash)
        fingerprint = ripemd160.digest()[:4]
        return fingerprint

    @staticmethod
    def get_wallet_data(private_master_key, private_master_code):

        wallet_finderprint = Bip44.fingerprint_hex(private_master_key)

        # Derivem amb index 44'   m/ a m/44' de forma endurida i optenim una child_key i un child_chain_code,
        purpose_index = 44
        purpose_key, purpose_chain_code = Bip44.child_key_hardened(
            private_master_key, private_master_code, purpose_index, hardened=True
        )

        # Derivem amb index 0'   m/ a m/44'/145' de forma endurida i optenim una child_key i un child_chain_code,
        coin_type_index = 145
        coin_type_key, coin_type_chain_code = Bip44.child_key_hardened(
            purpose_key, purpose_chain_code, coin_type_index, hardened=True
        )

        # Derivem amb index 0'   m/ a m/44/145'/0' de forma endurida i optenim una child_key i un child_chain_code,
        account_index = 0
        account_key, account_chain_code = Bip44.child_key_hardened(
            coin_type_key, coin_type_chain_code, account_index, hardened=True
        )
        account_public_key = Bip44.public_master_key_compressed_generaitor(account_key)

        # Retornem tambe variables comunes i nessesaries en xpriv i xpub:
        # Depth
        depth = 3
        depth = depth.to_bytes(1, byteorder="big")

        # finerprint del pare
        father_acount_publickey = Bip44.public_master_key_compressed_generaitor(
            coin_type_key
        )
        father_fingerprint = Bip44.fingerprint_bytes(father_acount_publickey)

        # child_index
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

        return xpriv, xpub, wallet_finderprint

    @staticmethod
    def convert_bits(data, from_bits, to_bits, pad=True):
        acc = 0
        bits = 0
        ret = []
        maxv = (1 << to_bits) - 1  # Màxim valor per un bloc de to_bits
        for value in data:
            acc = (acc << from_bits) | value  # Afegeix el nou valor
            bits += from_bits
            while bits >= to_bits:
                bits -= to_bits
                ret.append((acc >> bits) & maxv)  # Extreu el bloc de to_bits
        if pad and bits:
            ret.append((acc << (to_bits - bits)) & maxv)  # Completa el bloc restant
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
        version_byte = 0x00  # Per P2PKH
        payload = bytes([version_byte]) + Bip44.hash160(pubkey)
        payload_5bit = Bip44.convert_bits(payload, 8, 5)
        checksum = Bip44.create_checksum("bitcoincash", payload_5bit)
        address = "bitcoincash:" + Bip44.encode_base32(payload_5bit + checksum)
        return address

    @staticmethod
    def hash160_to_cashaddr(hash160: bytes) -> str:
        """Convert a 20-byte HASH160 to a bitcoincash cashaddr string (P2PKH payload)."""
        if len(hash160) != 20:
            raise ValueError("hash160 must be 20 bytes")
        version_byte = 0x00
        payload = bytes([version_byte]) + hash160
        payload_5bit = Bip44.convert_bits(payload, 8, 5)
        checksum = Bip44.create_checksum("bitcoincash", payload_5bit)
        address = "bitcoincash:" + Bip44.encode_base32(payload_5bit + checksum)
        return address

    @staticmethod
    def xpub_to_cashaddr_address(xpub, address_index):

        (
            version,
            depth,
            fingerprint,
            child_number,
            chain_code_chain,
            public_key_chain,
        ) = Bip44.xpub_decode(
            xpub
        )  # m/44'/145'/0'

        child_public_chain, child_chain_chain = Bip44.derive_public_child_key(
            public_key_chain, chain_code_chain, 0
        )  # m/44'/145'/0'/0
        child_public_address_index, child_chain_address_index = (
            Bip44.derive_public_child_key(
                child_public_chain, child_chain_chain, address_index
            )
        )  # m/44'/145'/0'/0/0
        address = Bip44.public_key_to_cashaddr_address(child_public_address_index)
        return address
