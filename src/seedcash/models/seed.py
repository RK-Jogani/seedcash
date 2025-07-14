import logging
import unicodedata
import hashlib
from seedcash.models import btc_functions as bf
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
            list_index_bi = [
                bin(self.wordlist.index(word))[2:].zfill(11) for word in self._mnemonic
            ]

            bin_mnemonic = "".join(list_index_bi)

            # checksum
            checksum = bin_mnemonic[-4:]

            decimal_mnemonic = int(bin_mnemonic[:-4], 2)

            n = len(bin_mnemonic)
            hexa_mnemonic = hex(decimal_mnemonic)[2:].zfill((n - 4) // 4)

            if len(hexa_mnemonic) % 2 != 0:  # If the length is odd, add a leading zero
                hexa_mnemonic = "0" + hexa_mnemonic

            # Convert to bytes
            # Convert the hexadecimal mnemonic to bytes
            byte_mnemonic = bytes.fromhex(hexa_mnemonic)

            # Hash i conversio a binari
            hash_object = hashlib.sha256()
            hash_object.update(byte_mnemonic)
            hexa_hashmnemonic = hash_object.hexdigest()
            bin_hashmnemonic = bin(int(hexa_hashmnemonic, 16))[2:].zfill(256)

            checksum_revised = bin_hashmnemonic[:4]

            if not checksum == checksum_revised:
                raise InvalidSeedException(repr(e))

        except Exception as e:
            logger.info(repr(e), exc_info=True)
            raise InvalidSeedException(repr(e))

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
