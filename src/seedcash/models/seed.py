import logging
import hashlib

from seedcash.models.bip39 import Bip39
from typing import List
from seedcash.gui.components import load_txt
from seedcash.models.wallet import Wallet

logger = logging.getLogger(__name__)


class InvalidSeedException(Exception):
    pass


class Seed:
    def __init__(self, mnemonic: List[str] = None) -> None:

        if not mnemonic:
            raise Exception(
                "Must initialize a Seed with a mnemonic List[str] or a master_secret"
            )

        self.mnemonic = mnemonic
        self.passphrase: str = ""
        self.wallet: Wallet = None

        self.validate_mnemonic()

    @property
    def _mnemonic(self) -> str:
        return " ".join(self.mnemonic)

    @property
    def _passphrase(self):
        return self.passphrase

    @property
    def _wallet(self) -> Wallet:
        return self.wallet

    @property
    def wordlist(self) -> List[str]:
        return load_txt("bip39.txt")

    def get_mnemonic_list(self) -> List[str]:
        return self.mnemonic

    def set_passphrase(self, passphrase: str):
        self.passphrase = passphrase

    def validate_mnemonic(self) -> bool:
        try:
            # Validate wordlist membership first
            list_index_bi = []
            for word in self.get_mnemonic_list():
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

    def generate_wallet(self):

        master_private_key, master_private_code = Bip39.bip39_protocol(
            self._mnemonic, self.passphrase
        )
        self.wallet = Wallet(master_private_key, master_private_code)
