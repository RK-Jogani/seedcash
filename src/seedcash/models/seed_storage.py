from typing import List
from seedcash.models.seed import Seed, InvalidSeedException
import logging

logger = logging.getLogger(__name__)


class SeedStorage:
    def __init__(self) -> None:
        self.mnemonic: List[str] = [None] * 12
        self.seed: Seed = None

    @property
    def _mnemonic(self) -> List[str]:
        return self.mnemonic

    @property
    def _mnemonic_length(self) -> int:
        return len(self.mnemonic)

    def update_mnemonic(self, word: str, index: int):
        """
        Replaces the nth word in the mnemonic.

        * may specify a negative `index` (e.g. -1 is the last word).
        """
        if index >= len(self.mnemonic):
            raise Exception(f"index {index} is too high")
        self.mnemonic[index] = word

    def get_mnemonic_word(self, index: int) -> str:
        if index < len(self.mnemonic):
            return self.mnemonic[index]
        return None

    def convert_mnemonic_to_seed(self) -> Seed:
        self.seed = Seed(mnemonic=self.mnemonic)
        self.discard_mnemonic()

    def discard_mnemonic(self):
        self.mnemonic = [None] * 12

    def get_seed(self) -> Seed:
        if not self.seed:
            raise InvalidSeedException("Seed has not been initialized")
        return self.seed

    def get_generated_seed(self) -> str:
        if not self.mnemonic:
            raise InvalidSeedException("Mnemonic has not been initialized")
        else:
            logger.info("Generating fingerprint from mnemonic: %s", self.mnemonic)
            mnemonic_seed = Seed(mnemonic=self.mnemonic)
            mnemonic_seed.generate_seed()
            return mnemonic_seed

    def set_mnemonic_length(self, length: int):
        if length not in [12, 15, 18, 21, 24]:
            raise ValueError(
                "Invalid mnemonic length. Must be one of [12, 15, 18, 21, 24]."
            )
        self.mnemonic = [None] * length
        logger.info(f"Mnemonic length set to {length} words.")
