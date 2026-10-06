from typing import List, Optional, Tuple
from seedcash.models.wallet import Wallet
from seedcash.models.seed import Seed, InvalidSeedException
from seedcash.models.scheme import Scheme, SchemeParameters, InvalidSchemeException
from seedcash.models.settings import Settings
from seedcash.models.settings_definition import SettingsConstants

import logging
from seedcash.gui.components import load_txt

logger = logging.getLogger(__name__)


class SeedStorage:
    def __init__(self) -> None:
        self._mnemonic: List[str] = None
        self._scheme: Scheme = None
        self._seed: Seed = None
        self._calculate_last_word_fields: Tuple[str, str] = None
        self._is_generate: bool = False

    @property
    def get_wordlist(self) -> List[str]:
        # getting world list from resource/bip39.txt
        if (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL)
            == "BIP39"
        ):
            list39 = load_txt("bip39.txt")
        elif (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL)
            == "SLIP39"
        ):
            list39 = load_txt("slip39.txt")

        return list39

    # Mnemonic management
    @property
    def mnemonic(self) -> List[str]:
        if self._mnemonic is None:
            raise InvalidSeedException("Mnemonic has not been initialized")
        return self._mnemonic

    def set_mnemonic(self, mnemonic: List[Optional[str]]):
        if not isinstance(mnemonic, list):
            raise InvalidSeedException("Mnemonic must be a list")
        # Allow None entries so we can clear the list
        if not all(word is None or isinstance(word, str) for word in mnemonic):
            raise InvalidSeedException("Mnemonic entries must be str or None")
        self._mnemonic = mnemonic

    def discard_mnemonic(self):
        if self._mnemonic is not None:
            self.mnemonic[:] = [None] * len(self.mnemonic)

    def get_mnemonic_word(self, index: int) -> str:
        if index < len(self.mnemonic):
            return self.mnemonic[index]
        return None

    def update_mnemonic(self, word: str, index: int):
        if index >= len(self.mnemonic):
            raise InvalidSeedException(f"index {index} is too high")
        self.mnemonic[index] = word

    @property
    def mnemonic_length(self) -> int:
        return len(self.mnemonic)
    
    def set_mnemonic_length(self, length: int):
        if length not in [12, 15, 18, 20, 21, 24, 33]:
            raise ValueError(
                "Invalid mnemonic length. Must be one of [12, 15, 18, 20, 21, 24, 33]."
            )
        self.set_mnemonic([None] * length)
        logger.info(f"Mnemonic length set to {length} words.")

    @property
    def passphrase(self) -> Optional[str]:
        if (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL) == "BIP39"
        ):
            return self.seed.passphrase
        elif (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL) == "SLIP39"
        ):
            
            return self.scheme.passphrase.decode("utf-8")

        return None

    def set_passphrase(self, passphrase: str):
        if (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL) == "BIP39"
        ):
            self.seed.set_passphrase(passphrase)
        elif (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL) == "SLIP39"
        ):
            self.scheme.set_passphrase(passphrase)

    # Seed management
    @property
    def seed(self) -> Seed:
        if not self._seed:
            raise InvalidSeedException("Seed has not been initialized")
        return self._seed

    def set_seed(self, seed: Seed):
        if not isinstance(seed, Seed):
            raise InvalidSeedException("Provided seed is not a valid Seed instance")
        self._seed = seed
        
    def convert_mnemonic_to_seed(self) -> Seed:
        self.set_seed(Seed(mnemonic=self.mnemonic))
        if self._calculate_last_word_fields is not None:
            self._calculate_last_word_fields = None
            
        self.discard_mnemonic()

    def calculate_final_word(self, coin_flips: str) -> str:        
        from seedcash.models.bip39 import Bip39
        self.set_mnemonic(Bip39.get_mnemonic(self.mnemonic[:-1], coin_flips))
        last_word_index = self.get_wordlist.index(self.mnemonic[-1])
        checksum_bits = format(last_word_index,"011b")[-self.mnemonic_length // 3:]
        self._calculate_last_word_fields: Tuple[str, str] = (coin_flips, checksum_bits)

    @property
    def calculate_last_word_fields(self) -> Tuple[str, str]:
        if self._calculate_last_word_fields is None:
            raise InvalidSeedException("Calculate last word fields have not been initialized")
        return self._calculate_last_word_fields


    def discard_seed(self):
        if self._seed is not None:
            self._seed.discard_seed()
        self._seed = None

    # Scheme management
    @property
    def scheme(self) -> Scheme:
        if not self._scheme:
            raise InvalidSchemeException("Scheme has not been initialized")
        return self._scheme
    
    def set_scheme(self, scheme: Scheme):
        if not isinstance(scheme, Scheme):
            raise InvalidSchemeException("Provided scheme is not a valid Scheme instance")
        self._scheme = scheme

    def discard_scheme(self):
        if self._scheme is not None:
            self._scheme.discard_scheme()
        self._scheme = None
    
    def set_scheme_params(self, bits: Optional[str] = None):
        if bits is not None:
            self.set_scheme(
                Scheme(scheme_parameters=SchemeParameters(bits=bits))
            )
        else:
            from seedcash.models.slip39 import Slip39 as sp
            self.set_scheme(
                Scheme(scheme_parameters=SchemeParameters(
                    bits=sp.get_random_bits_for_slip(self.mnemonic_length)
                    )
                ))

        logger.info(f"Scheme and Mnemonics generated with parameters")

    def add_share_to_scheme(self):
        
        if self.is_generate:
            logger.warning("Cannot add share to scheme after wallet generation.")
            raise InvalidSchemeException("Cannot add share to scheme after wallet generation.")

        if self._scheme is None:
            self.set_scheme(Scheme())
            
        try:
            self.scheme.add_share(self.mnemonic)
            logger.info("Share added to the current scheme.")
        except InvalidSchemeException as e:
            logger.warning(f"Invalid SLIP39 share {e}")
            raise InvalidSchemeException(f"Invalid mnemonic provided for scheme {e}")

    @property
    def wallet(self) -> Optional[Wallet]:
        if (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL)
            == "BIP39"
        ):
            return self.seed.wallet
        elif (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL)
            == "SLIP39"
        ):
            return self.scheme.wallet

    def create_wallet(self):
        if (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL)
            == "BIP39"
        ):
            self.seed.generate_wallet()

        elif (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL)
            == "SLIP39"
        ):
            self.scheme.generate_wallet()

    def discard_wallet(self):
        # 1. Discard seed
        self.discard_seed()
        # 2. Discard scheme
        self.discard_scheme()
        self.discard_mnemonic()
    
        # 3. Force a collection attempt
        import gc
        gc.collect()
    
        logger.info("Wallet discarded (best-effort clear).")
