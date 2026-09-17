from typing import List, Optional
from seedcash.models.wallet import Wallet
from seedcash.models.seed import Seed, InvalidSeedException
from seedcash.models.scheme import Scheme, SchemeParameters, InvalidShareException, InvalidSchemeException
from seedcash.models.settings import Settings
from seedcash.models.settings_definition import SettingsConstants

import logging
from seedcash.gui.components import load_txt

logger = logging.getLogger(__name__)


class SeedStorage:
    def __init__(self) -> None:
        self.mnemonic: List[str] = None
        self.scheme_params: SchemeParameters = None
        self.passphrase: str = ""
        self.scheme: Scheme = None
        self.seed: Seed = None
        self.wallet: Wallet = None

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

    @property
    def _wallet(self) -> Wallet:
        if not self.wallet:
            raise InvalidSeedException("Wallet has not been initialized")
        return self.wallet

    def create_wallet(self):
        if (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL)
            == "BIP39"
        ):
            if not self.seed:
                raise InvalidSeedException("Seed must be initialized for BIP39.")
            self.seed.set_passphrase(self.passphrase)
            self.seed.generate_wallet()
            self.wallet = self.seed._wallet

        elif (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL)
            == "SLIP39"
        ):
            if not self.scheme:
                raise InvalidSchemeException("Scheme must be initialized for SLIP39.")
            self.scheme.set_passphrase(self.passphrase)
            self.scheme.generate_wallet()
            self.wallet = self.scheme._wallet

    def discard_wallet(self):
        # 1. Clear nested objects first (if they exist)
        if self.seed is not None:
            self.discard_seed()
    
        if self.scheme is not None:
            self.discard_scheme()
        
        if self.wallet is not None:
            self.wallet.discard_wallet()
        self.wallet = None

        self.passphrase = ""
        self.discard_mnemonic()
    
        # 3. Force a collection attempt
        import gc
        gc.collect()
    
        logger.info("Wallet discarded (best-effort clear).")

    # Mnemonic management
    @property
    def _mnemonic(self) -> List[str]:
        if self.mnemonic is None:
            raise InvalidSeedException("Mnemonic has not been initialized")
        return self.mnemonic

    @property
    def mnemonic_length(self) -> int:
        return len(self._mnemonic)

    def set_mnemonic(self, mnemonic: List[Optional[str]]):
        if not isinstance(mnemonic, list):
            raise InvalidSeedException("Mnemonic must be a list")
        # Allow None entries so we can clear the list
        if not all(word is None or isinstance(word, str) for word in mnemonic):
            raise InvalidSeedException("Mnemonic entries must be str or None")
        self.mnemonic = mnemonic

    def set_mnemonic_length(self, length: int):
        if length not in [12, 15, 18, 20, 21, 24, 33]:
            raise ValueError(
                "Invalid mnemonic length. Must be one of [12, 15, 18, 20, 21, 24, 33]."
            )
        self.set_mnemonic([None] * length)
        logger.info(f"Mnemonic length set to {length} words.")

    def discard_mnemonic(self):
        if self.mnemonic is not None:
            self.set_mnemonic([None] * len(self.mnemonic))

    def get_mnemonic_word(self, index: int) -> str:
        if index < len(self.mnemonic):
            return self.mnemonic[index]
        return None

    def update_mnemonic(self, word: str, index: int):
        """
        Replaces the nth word in the mnemonic.

        * may specify a negative `index` (e.g. -1 is the last word).
        """
        if index >= len(self.mnemonic):
            raise InvalidSeedException(f"index {index} is too high")
        self.mnemonic[index] = word

    # Passphrase management
    @property
    def _passphrase(self):
        if not self.passphrase:
            raise InvalidSeedException("Passphrase not initialize")
        return self.passphrase

    def set_passphrase(self, passphrase: str):
        self.passphrase = passphrase

    # Seed management
    @property
    def _seed(self) -> Seed:
        if not self.seed:
            raise InvalidSeedException("Seed has not been initialized")
        return self.seed

    def set_seed(self, seed: Seed):
        if not isinstance(seed, Seed):
            raise InvalidSeedException("Provided seed is not a valid Seed instance")
        self.seed = seed
        
    def convert_mnemonic_to_seed(self) -> Seed:
        self.seed = Seed(mnemonic=self._mnemonic)
        self.discard_mnemonic()

    def get_seed_wallet(self) -> Wallet:
        """
        Get the wallet associated with the current seed.
        """
        if not self.seed:
            raise InvalidSeedException("Seed has not been initialized")

        self.seed.set_passphrase(self.passphrase)
        self.seed.generate_wallet()

        return self.seed._wallet

    def discard_seed(self):
        """
        Discard the current seed.
        """
        self.discard_mnemonic()
        self.passphrase = ""
        self.seed.discard_seed()
        self.seed = None

    # Scheme management
    @property
    def _scheme(self) -> Scheme:
        if not self.scheme:
            raise InvalidSchemeException("Scheme has not been initialized")
        return self.scheme

    def set_scheme_params(self, bits: str):
        """
        Set the scheme parameters for the current seed.
        """
        if not bits:
            raise InvalidSchemeException("Bits must be provided to set scheme parameters")

        self.scheme_params = SchemeParameters(bits=bits)
        logger.info("Scheme parameters set with bits: %s", bits)

    def generate_scheme_with_params(self):
        """
        Generate a scheme based on the current mnemonic and scheme parameters.
        """
        if not self.scheme_params:
            raise InvalidSchemeException("Scheme parameters have not been set")

        self.scheme = Scheme(
            scheme_parameters=self.scheme_params,
        )
        self.scheme.set_passphrase(self.passphrase)
        self.scheme.generate_mnemonics()
        self.scheme.generate_wallet()
        logger.info("Scheme generated with parameters: %s", self.scheme_params)

    def add_share_to_scheme(self):
        """
        Add the current slip mnemonic as a share.
        - First call: create Scheme from this share
        - Later calls: add share to the existing recovery scheme
        """

        if self.mnemonic is None:
            raise InvalidShareException("Mnemonic has not been initialized")

        # Reject incomplete entry (still has None placeholders)
        if any(w is None or not isinstance(w, str) for w in self.mnemonic):
            raise InvalidShareException("Mnemonic is incomplete")

        # Generation path already used scheme_parameters — do not mix with recovery
        if self.scheme is not None and self.scheme.scheme_parameters is not None:
            raise InvalidSchemeException("Scheme was generated with parameters; cannot add recovery shares")

        try:
            if self.scheme is None:
                self.scheme = Scheme(mnemonics=self._mnemonic)
                logger.info("New scheme created from first share.")
            else:
                self.scheme.add_share(self._mnemonic)
                logger.info("Share added to the current scheme.")
        except InvalidSchemeException as e:
            logger.exception("Invalid SLIP39 share: %s", e)
            raise InvalidSchemeException("Invalid mnemonic provided for scheme") from e
        finally:
            # Always clear the temporary slip mnemonic after attempt
            self.discard_slip_mnemonic()

    def discard_slip_mnemonic(self):
        """
        Discard the current mnemonic used for SLIP39 scheme.
        """
        self.discard_mnemonic()
        logger.info("SLIP39 mnemonic discarded.")

    def discard_scheme(self):
        """
        Discard the current scheme.
        """
        if self.scheme is not None:
            self.scheme.discard_scheme()
        self.scheme = None
        if self.scheme_params is not None:
            self.scheme_params.discard_parameters()
        self.scheme_params = None
        self.passphrase = ""
        self.discard_slip_mnemonic()
        logger.info("Scheme and parameters discarded.")
