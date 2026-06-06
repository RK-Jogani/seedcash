from typing import List
from seedcash.models.seed import Seed, InvalidSeedException
import logging

logger = logging.getLogger(__name__)


class SeedStorage:
    def __init__(self) -> None:
        self._mnemonic: List[str] = [None] * 12
        self.seed: Seed = None

    @property
    def mnemonic(self) -> List[str]:
        # Always return a copy so that the internal List can't be altered
        return list(self._mnemonic)

    @property
    def mnemonic_length(self) -> int:
        return len(self._mnemonic)

    def update_mnemonic(self, word: str, index: int):
        """
        Replaces the nth word in the mnemonic.

        * may specify a negative `index` (e.g. -1 is the last word).
        """
        if index >= len(self._mnemonic):
            raise Exception(f"index {index} is too high")
        self._mnemonic[index] = word

    def get_mnemonic_word(self, index: int) -> str:
        if index < len(self._mnemonic):
            return self._mnemonic[index]
        return None

    def convert_mnemonic_to_seed(self) -> Seed:
        self.seed = Seed(mnemonic=self._mnemonic)
        self.discard_mnemonic()

    def discard_mnemonic(self):
        self._mnemonic = [None] * 12

    def get_seed(self) -> Seed:
        if not self.seed:
            raise InvalidSeedException("Seed has not been initialized")
        return self.seed

    def get_generated_seed(self) -> str:
        if not self._mnemonic:
            raise InvalidSeedException("Mnemonic has not been initialized")
        else:
            logger.info("Generating fingerprint from mnemonic: %s", self._mnemonic)
            mnemonic_seed = Seed(mnemonic=self._mnemonic)
            mnemonic_seed.generate_seed()
            return mnemonic_seed

    def set_mnemonic_length(self, length: int):
        if length not in [12, 15, 18, 21, 24]:
            raise ValueError(
                "Invalid mnemonic length. Must be one of [12, 15, 18, 21, 24]."
            )
        self._mnemonic = [None] * length
        logger.info(f"Mnemonic length set to {length} words.")
