import hashlib
import hmac
import os

from seedcash.gui.components import load_txt


class Bip39:
    @staticmethod
    def dictionary_BIP39():
        """Llegim el diccionari Bip39"""

        list39 = load_txt("bip39.txt")
        return list39

    @staticmethod
    def binmnemonic_to_mnemonic(bin_mnemonic):
        list39 = Bip39.dictionary_BIP39()
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

    @staticmethod
    def get_mnemonic(incomplete_mnemonic, last_bits):

        len_checksum = 11 - len(last_bits)
        string_mnemonic = " ".join(incomplete_mnemonic)

        list39 = Bip39.dictionary_BIP39()
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
        mnemonic = Bip39.binmnemonic_to_mnemonic(bits_mnemonic)
        print("The mnemonic:", mnemonic)
        return mnemonic

    @staticmethod
    def generate_hexa_seed(seed, passphrase):
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
    def bip39_protocol(seed: str, passphrase: str):
        # Replacing this part from get private_and_code method
        """Genera la clave privada maestra y el código de cadena a partir de una semilla en hexadecimal"""

        hexa_seed = Bip39.generate_hexa_seed(seed, passphrase)

        hmac_hash = hmac.new(
            b"Bitcoin seed", bytes.fromhex(hexa_seed), hashlib.sha512
        ).digest()

        private_master_key = hmac_hash[:32]
        private_master_code = hmac_hash[32:]

        return private_master_key, private_master_code

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
        mnemonic = Bip39.binmnemonic_to_mnemonic(full_binary)

        return mnemonic
