import logging
import unicodedata
import hashlib

from seedcash.models.btc_functions import BitcoinFunctions as bf
from typing import List
from seedcash.gui.components import load_txt

logger = logging.getLogger(__name__)


class InvalidSeedException(Exception):
    pass


class Seed:
    def __init__(self, mnemonic: List[str] = None) -> None:

        if not mnemonic:
            raise Exception("Must initialize a Seed with a mnemonic List[str]")

        # variables
        self._mnemonic = mnemonic
        self._passphrase: str = ""
        self.xpriv: str = ""
        self.xpub: str = ""
        self.fingerprint: str = ""

        self._validate_mnemonic()

    # this method will be replace by seedcash
    @staticmethod
    def get_wordlist() -> List[str]:
        # getting world list from resource/bip39.txt
        list39 = load_txt("bip39.txt")
        return list39

    def _validate_mnemonic(self):
        try:
            # Validate wordlist membership first
            list_index_bi = []
            for word in self._mnemonic:
                try:
                    index = self.wordlist.index(word)
                    list_index_bi.append(bin(index)[2:].zfill(11))
                except ValueError:
                    raise InvalidSeedException(f"Word '{word}' not in wordlist")

            bin_mnemonic = "".join(list_index_bi)
            len_ = len(bin_mnemonic)

            # Validate length and determine checksum bits
            checksum_bits = None
            if len_ == 132:  # 12 words
                checksum_bits = 4
            elif len_ == 165:  # 15 words
                checksum_bits = 5
            elif len_ == 198:  # 18 words
                checksum_bits = 6
            elif len_ == 231:  # 21 words
                checksum_bits = 7
            elif len_ == 264:  # 24 words
                checksum_bits = 8
            else:
                raise InvalidSeedException("Invalid mnemonic length")

            # Extract checksum
            checksum = bin_mnemonic[-checksum_bits:]

            # Convert entropy to bytes
            entropy_bits = bin_mnemonic[:-checksum_bits]
            # Ensure we have complete bytes
            if len(entropy_bits) % 8 != 0:
                raise InvalidSeedException("Invalid entropy length")

            # Convert to bytes
            entropy_int = int(entropy_bits, 2)
            entropy_bytes = entropy_int.to_bytes(
                len(entropy_bits) // 8, byteorder="big"
            )

            # Compute SHA256 hash
            hash_bytes = hashlib.sha256(entropy_bytes).digest()
            hash_int = int.from_bytes(hash_bytes, byteorder="big")
            computed_checksum = bin(hash_int)[2:].zfill(256)[:checksum_bits]

            if checksum != computed_checksum:
                logger.debug(
                    "Checksum mismatch: expected %s, got %s",
                    checksum,
                    computed_checksum,
                )
                raise InvalidSeedException("Checksum validation failed")

            return True

        except InvalidSeedException:
            raise
        except Exception as e:
            logger.exception("Unexpected error during validation")
            raise InvalidSeedException(f"Validation error: {str(e)}")

    def generate_seed(self) -> bytes:
        hexa_seed = bf.seed_generator(self.mnemonic_str, self.passphrase)

        (
            depth,
            father_fingerprint,
            child_index,
            account_chain_code,
            account_key,
            account_public_key,
        ) = bf.derivation_m_44_145_0(hexa_seed)

        self.xpriv = bf.xpriv_encode(
            depth, father_fingerprint, child_index, account_chain_code, account_key
        )

        self.xpub = bf.xpub_encode(
            depth,
            father_fingerprint,
            child_index,
            account_chain_code,
            account_public_key,
        )

        self.fingerprint = bf.fingerprint_hex(hexa_seed)

    @property
    def mnemonic_str(self) -> str:
        return " ".join(self._mnemonic)

    @property
    def mnemonic_list(self) -> List[str]:
        return self._mnemonic

    @property
    def wordlist_language_code(self) -> str:
        return self._wordlist_language_code

    @property
    def mnemonic_display_str(self) -> str:
        return unicodedata.normalize("NFC", " ".join(self._mnemonic))

    @property
    def mnemonic_display_list(self) -> List[str]:
        return unicodedata.normalize("NFC", " ".join(self._mnemonic)).split()

    @property
    def has_passphrase(self):
        return self._passphrase != ""

    @property
    def passphrase(self):
        return self._passphrase

    @property
    def passphrase_display(self):
        return unicodedata.normalize("NFC", self._passphrase)

    def set_passphrase(self, passphrase: str):
        self._passphrase = passphrase

    @property
    def wordlist(self) -> List[str]:
        return Seed.get_wordlist()

    def get_fingerprint(self) -> str:
        return self.fingerprint

    ### override operators
    def __eq__(self, other):
        if isinstance(other, Seed):
            return self.seed_bytes == other.seed_bytes
        return False
