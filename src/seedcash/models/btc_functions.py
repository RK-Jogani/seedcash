import hashlib
import hmac
import os

from base58 import b58decode, b58encode

from ecdsa import SECP256k1, SigningKey, VerifyingKey
from ecdsa.util import string_to_number, number_to_string
from seedcash.gui.components import load_txt

import logging

logger = logging.getLogger(__name__)


class BitcoinFunctions:

    @staticmethod
    def sha256(data):
        return hashlib.sha256(data).digest()

    @staticmethod
    def hmac_sha512(key, data):
        return hmac.new(key, data, hashlib.sha512).digest()

    @staticmethod
    def hash160(pubkey):
        sha256_hash = hashlib.sha256(pubkey).digest()
        ripemd160_hash = hashlib.new("ripemd160", sha256_hash).digest()
        return ripemd160_hash

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
    def encode_base32(data):
        CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        return "".join([CHARSET[d] for d in data])

    @staticmethod
    def dictionary_BIP39():
        """Llegim el diccionari Bip39"""

        list39 = load_txt("bip39.txt")
        return list39

    @staticmethod
    def binmnemonic_to_mnemonic(bin_mnemonic):
        list39 = BitcoinFunctions.dictionary_BIP39()
        n = len(bin_mnemonic)
        mnemonic = []
        index = []
        for i in range(0, n, 11):
            block = bin_mnemonic[i : i + 11]
            index_word = int(block, 2)
            index.append(index_word)
        for index_word in index:
            word = list39[index_word]
            mnemonic.append(word)
        return mnemonic

    # calculate the last word with bits
    @staticmethod
    def get_mnemonic(incomplete_mnemonic, last_bits):

        len_checksum = 11 - len(last_bits)

        logger.info(
            "Generating mnemonic from incomplete mnemonic: %s and last bits: %s",
            incomplete_mnemonic,
            last_bits,
        )
        string_mnemonic = " ".join(incomplete_mnemonic)

        logger.info("String mnemonic: %s", string_mnemonic)

        list39 = BitcoinFunctions.dictionary_BIP39()
        list_mnemonic = string_mnemonic.strip().split()

        list_index_bi = [
            bin(list39.index(word))[2:].zfill(11) for word in list_mnemonic
        ]
        first_bits = "".join(list_index_bi)
        initial_bits = first_bits + last_bits

        decimal_incomplet_mnemonic = int(initial_bits, 2)
        hexa_incomplet_mnemonic = hex(decimal_incomplet_mnemonic)[2:].zfill(
            (len(initial_bits) + 7) // 8 * 2
        )
        byte_incomplet_mnemonic = bytes.fromhex(hexa_incomplet_mnemonic)

        hash_object = hashlib.sha256()
        hash_object.update(byte_incomplet_mnemonic)
        hexa_hashmnemonic = hash_object.hexdigest()
        bin_hashmnemonic = bin(int(hexa_hashmnemonic, 16))[2:].zfill(256)

        checksum = bin_hashmnemonic[:len_checksum]

        bits_mnemonic = initial_bits + checksum
        mnemonic = BitcoinFunctions.binmnemonic_to_mnemonic(bits_mnemonic)
        print("The mnemonic:", mnemonic)
        return mnemonic

    @staticmethod
    def seed_generator(seed, passphrase):
        """mnemonic + passprhrase --> seed   (512bits=64bytes)"""

        # Convertim a bytes els inputs
        mnemonic_bytes = seed.encode("utf-8")
        passphrase_bytes = passphrase.encode("utf-8")

        # PBKDF2
        algorithm = "sha512"
        salt_bytes = b"mnemonic" + passphrase_bytes
        iterations = 2048
        key_length = 64

        bytes_seed = hashlib.pbkdf2_hmac(
            algorithm, mnemonic_bytes, salt_bytes, iterations, key_length
        )
        hexa_final_seed = bytes_seed.hex()
        return hexa_final_seed

    @staticmethod
    def get_private_and_code(seed):
        """Genera la clave privada maestra y el código de cadena a partir de una semilla en hexadecimal"""
        hmac_hash = hmac.new(
            b"Bitcoin seed", bytes.fromhex(seed), hashlib.sha512
        ).digest()
        private_master_key = hmac_hash[:32]
        private_master_code = hmac_hash[32:]
        return private_master_key, private_master_code

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
    def child_key_hardened(parent_key, parent_chain_code, index, hardened=False):
        curve_order = SECP256k1.order
        if hardened:
            index |= 0x80000000
        index_bytes = index.to_bytes(4, "big")
        data = b"\x00" + parent_key + index_bytes
        I = BitcoinFunctions.hmac_sha512(parent_chain_code, data)

        Il = I[:32]
        chain_code = I[32:]

        number_Il = string_to_number(Il)
        number_parent = string_to_number(parent_key)
        number_derived = (number_Il + number_parent) % curve_order

        derivet_key = number_to_string(number_derived, curve_order)

        return derivet_key, chain_code

    @staticmethod
    def derivation_m_44_145_0(hexa_seed):
        # Donada una seed trobem privat key i chain code (m/)
        private_master_key, private_master_code = BitcoinFunctions.get_private_and_code(
            hexa_seed
        )

        # Derivem amb index 44'   m/ a m/44' de forma endurida i optenim una child_key i un child_chain_code,
        purpose_index = 44
        purpose_key, purpose_chain_code = BitcoinFunctions.child_key_hardened(
            private_master_key, private_master_code, purpose_index, hardened=True
        )

        # Derivem amb index 0'   m/ a m/44'/145' de forma endurida i optenim una child_key i un child_chain_code,
        coin_type_index = 145
        coin_type_key, coin_type_chain_code = BitcoinFunctions.child_key_hardened(
            purpose_key, purpose_chain_code, coin_type_index, hardened=True
        )

        # Derivem amb index 0'   m/ a m/44/145'/0' de forma endurida i optenim una child_key i un child_chain_code,
        account_index = 0
        account_key, account_chain_code = BitcoinFunctions.child_key_hardened(
            coin_type_key, coin_type_chain_code, account_index, hardened=True
        )
        account_public_key = BitcoinFunctions.public_master_key_compressed_generaitor(
            account_key
        )

        # Retornem tambe variables comunes i nessesaries en xpriv i xpub:
        # Depth
        depth = 3
        depth = depth.to_bytes(1, byteorder="big")

        # finerprint del pare
        father_acount_publickey = (
            BitcoinFunctions.public_master_key_compressed_generaitor(coin_type_key)
        )
        father_fingerprint = BitcoinFunctions.fingerprint_bytes(father_acount_publickey)

        # child_index
        child_index = 0 | 0x80000000
        child_index = child_index.to_bytes(4, byteorder="big")

        return (
            depth,
            father_fingerprint,
            child_index,
            account_chain_code,
            account_key,
            account_public_key,
        )

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
        checksum = BitcoinFunctions.sha256(BitcoinFunctions.sha256(data))[:4]

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
        checksum = BitcoinFunctions.sha256(BitcoinFunctions.sha256(data))[:4]

        return b58encode(data + checksum).decode("utf-8")

    @staticmethod
    def fingerprint_hex(hexa_seed):
        """Donada una compressed_master_public_key_bytes retorna un master fingerprint en hexadecimal"""

        (
            depth,
            father_fingerprint,
            child_index,
            account_chain_code,
            account_key,
            account_public_key,
        ) = BitcoinFunctions.derivation_m_44_145_0(hexa_seed)

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
        ) = BitcoinFunctions.xpub_decode(
            xpub
        )  # m/44'/145'/0'

        child_public_chain, child_chain_chain = (
            BitcoinFunctions.derive_public_child_key(
                public_key_chain, chain_code_chain, 0
            )
        )  # m/44'/145'/0'/0
        child_public_address_index, child_chain_address_index = (
            BitcoinFunctions.derive_public_child_key(
                child_public_chain, child_chain_chain, address_index
            )
        )  # m/44'/0'/0'/0/0
        address = BitcoinFunctions.public_key_to_legacy_address(
            child_public_address_index
        )

        return address

    # Cashaddr address generator
    @staticmethod
    def create_checksum(prefix, payload):
        values = [ord(x) & 0x1F for x in prefix] + [0] + payload
        polymod_result = BitcoinFunctions.polymod(values + [0, 0, 0, 0, 0, 0, 0, 0])
        return [(polymod_result >> (5 * (7 - i))) & 0x1F for i in range(8)]

    @staticmethod
    def public_key_to_cashaddr_address(pubkey):
        version_byte = 0x00  # Per P2PKH
        payload = bytes([version_byte]) + BitcoinFunctions.hash160(pubkey)
        payload_5bit = BitcoinFunctions.convert_bits(payload, 8, 5)
        checksum = BitcoinFunctions.create_checksum("bitcoincash", payload_5bit)
        address = "bitcoincash:" + BitcoinFunctions.encode_base32(
            payload_5bit + checksum
        )
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
        ) = BitcoinFunctions.xpub_decode(
            xpub
        )  # m/44'/145'/0'

        child_public_chain, child_chain_chain = (
            BitcoinFunctions.derive_public_child_key(
                public_key_chain, chain_code_chain, 0
            )
        )  # m/44'/145'/0'/0
        child_public_address_index, child_chain_address_index = (
            BitcoinFunctions.derive_public_child_key(
                child_public_chain, child_chain_chain, address_index
            )
        )  # m/44'/145'/0'/0/0
        address = BitcoinFunctions.public_key_to_cashaddr_address(
            child_public_address_index
        )
        return address

    @staticmethod
    def generate_random_seed(num_words: int = 12) -> list:
        """
        Generate a random num_words BIP39 mnemonic seed using OS random bits.

        Args:
            num_words: Number of words in the mnemonic (12, 15, 18, 21, or 24)

        Returns:
            list: List of num_words mnemonic words
        """
        # Validate num_words
        if num_words not in [12, 15, 18, 21, 24]:
            raise ValueError("Number of words must be 12, 15, 18, 21, or 24")

        # Calculate entropy bits needed (ENT)
        # For BIP39: ENT = (num_words * 11) - checksum_bits
        # Checksum bits = ENT / 32
        entropy_bits = (num_words * 11 * 32) // 33
        checksum_bits = entropy_bits // 32

        # Calculate entropy bytes needed
        entropy_bytes_count = entropy_bits // 8

        # Generate random entropy using os.urandom (cryptographically secure)
        entropy_bytes = os.urandom(entropy_bytes_count)

        # Convert bytes to binary string
        entropy_binary = "".join(format(byte, "08b") for byte in entropy_bytes)

        # Calculate SHA256 hash for checksum
        hash_object = hashlib.sha256()
        hash_object.update(entropy_bytes)
        hash_hex = hash_object.hexdigest()
        hash_binary = bin(int(hash_hex, 16))[2:].zfill(256)

        # Get first checksum_bits as checksum
        checksum = hash_binary[:checksum_bits]

        # Combine entropy and checksum
        full_binary = entropy_binary + checksum

        # Convert to mnemonic words using existing function
        mnemonic = BitcoinFunctions.binmnemonic_to_mnemonic(full_binary)

        logger.info(
            f"Generated {num_words}-word mnemonic with {entropy_bits} bits of entropy"
        )

        return mnemonic
