import hashlib
import hmac
import unicodedata

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

    def mnemonic_from_bytes(segment):
        """Convertim un segment de bytes a mnemonic"""
        # Convertim a binari
        bin_segment = "".join(format(byte, "08b") for byte in segment)
        entropy_hash = hashlib.sha256(segment).digest()

        # Determine checksum bits: ENT / 32
        checksum_bits = len(bin_segment) // 32  # 4 for 128-bit, 8 for 256-bit
        checksum = format(entropy_hash[0], '08b')[:checksum_bits]

        # Append checksum to entropy
        full_binary = bin_segment + checksum

        return Bip39.binmnemonic_to_mnemonic(full_binary)
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
        return mnemonic

    @staticmethod
    def generate_hexa_seed(seed: list[str], passphrase):
        """mnemonic + passprhrase --> seed   (512bits=64bytes)"""

        # Convertim a bytes els inputs
        mnemonic_str = unicodedata.normalize("NFKD", " ".join(seed))
        passphrase_str = unicodedata.normalize("NFKD", passphrase)

        mnemonic_bytes = mnemonic_str.encode("utf-8")
        passphrase_bytes = passphrase_str.encode("utf-8")

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
    def bip39_protocol(seed: list[str], passphrase: str):
        
        if passphrase is None:
            passphrase = ""
            
        hexa_seed = Bip39.generate_hexa_seed(seed, passphrase)

        hmac_hash = hmac.new(
            b"Bitcoin seed", bytes.fromhex(hexa_seed), hashlib.sha512
        ).digest()

        private_master_key = hmac_hash[:32]
        private_master_code = hmac_hash[32:]

        return private_master_key, private_master_code