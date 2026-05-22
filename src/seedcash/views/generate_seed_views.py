import logging

from gettext import gettext as _
from seedcash.models.bip39 import Bip39
from seedcash.gui.screens import RET_CODE__BACK_BUTTON
from seedcash.gui.screens.screen import ButtonOption
from seedcash.models.settings import Settings
from seedcash.models.settings_definition import SettingsConstants
from seedcash.views.view import (
    View,
    Destination,
    BackStackView,
    SeedCashChooseWordsView,
)

logger = logging.getLogger(__name__)

"""**************************************************
Seed Cash Updated Code
**************************************************"""


# First Generate Seed View
class SeedCashGenerateSeedView(View):
    def __init__(self):
        super().__init__()
        self.RANDOM_SEED = ButtonOption("Random Seed")

        self.CALCULATE_SEED = ButtonOption(
            "Calculate Last Word"
            if (
                Settings.get_instance().get_value(
                    SettingsConstants.SETTING__SEED_PROTOCOL
                )
                == SettingsConstants.SEED_PROTOCOL__BIP39
            )
            else "Custom Entropy Seed"
        )

    def run(self):
        from seedcash.gui.screens.generate_seed_screens import (
            SeedCashGenerateSeedScreen,
        )

        button_data = [self.RANDOM_SEED, self.CALCULATE_SEED]

        selected_menu_num = self.run_screen(
            SeedCashGenerateSeedScreen,
            button_data=button_data,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if button_data[selected_menu_num] == self.CALCULATE_SEED:
            return Destination(
                SeedCashChooseWordsView, view_args=dict(is_calc_final_word=True)
            )
        elif button_data[selected_menu_num] == self.RANDOM_SEED:
            return Destination(
                SeedCashChooseWordsView, view_args=dict(is_random_seed=True)
            )

        return Destination(BackStackView)


class SeedCashGenerateSeedRandomView(View):
    """View to generate a random seed and display the words."""

    def __init__(self):
        super().__init__()

    def run(self):
        # Generate a random mnemonic
        num_words = self.controller.storage.mnemonic_length
        mnemonic = Bip39.generate_random_seed(num_words=num_words)
        from seedcash.views.generate_seed_views import ShowWordsView

        return Destination(ShowWordsView, view_args={"mnemonic": mnemonic})


class ShowWordsView(View):
    def __init__(self, mnemonic: list = None):
        super().__init__()
        if mnemonic:
            self.controller.storage._mnemonic = mnemonic

        self.mnemonic = self.controller.storage.mnemonic

    def run(self):
        from seedcash.gui.screens.load_seed_screens import SeedCashSeedWordsScreen

        confirm = self.run_screen(
            SeedCashSeedWordsScreen,
            seed_words=self.mnemonic,
        )

        if confirm == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif confirm == "CONFIRM":
            from seedcash.views.wallet_views import WalletFinalizeView

            self.controller.storage.convert_mnemonic_to_seed()
            return Destination(
                WalletFinalizeView,
                view_args={"wallet": self.controller.storage.get_seed_wallet()},
            )


class ToolsCalcFinalWordCoinFlipsView(View):
    def run(self):
        from seedcash.gui.screens.generate_seed_screens import ToolsCoinFlipEntryScreen

        mnemonic_length = len(self.controller.storage._mnemonic)

        total_bits = 11 - (mnemonic_length // 3)

        ret_val = ToolsCoinFlipEntryScreen(
            return_after_n_chars=total_bits,
        ).display()

        if ret_val == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        else:
            return Destination(
                ToolsCalcFinalWordShowFinalWordView, view_args=dict(last_bits=ret_val)
            )


class ToolsCalcFinalWordShowFinalWordView(View):
    CONFIRM = ButtonOption("Confirm")

    def __init__(self, last_bits: str = None):
        super().__init__()

        wordlist = self.controller.storage.get_wordlist
        # Prep the user's selected word / coin flips and the actual final word for
        # the display.

        self.selected_final_bits = last_bits

        final_mnemonic = Bip39.get_mnemonic(
            self.controller.storage._mnemonic[:-1], last_bits
        )

        # Update our pending mnemonic with the real final word
        self.controller.storage.update_mnemonic(final_mnemonic[-1], -1)

        mnemonic = self.controller.storage._mnemonic
        mnemonic_length = len(mnemonic)

        # And grab the actual final word's checksum bits
        self.actual_final_word = self.controller.storage._mnemonic[-1]
        self.num_checksum_bits = mnemonic_length // 3
        self.checksum_bits = format(wordlist.index(self.actual_final_word), "011b")[
            -self.num_checksum_bits :
        ]

    def run(self):
        from seedcash.gui.screens.generate_seed_screens import ToolsCalcFinalWordScreen

        button_data = [self.CONFIRM]

        selected_menu_num = self.run_screen(
            ToolsCalcFinalWordScreen,
            button_data=button_data,
            num_checksum_bits=self.num_checksum_bits,
            selected_final_bits=self.selected_final_bits,
            checksum_bits=self.checksum_bits,
            actual_final_word=self.actual_final_word,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        elif button_data[selected_menu_num] == self.CONFIRM:
            return Destination(ShowWordsView)


class ToolsCalcFinalWordDoneView(View):
    FINISH = ButtonOption("Finish")
    PASSPHRASE = ButtonOption("Add Passphrase")

    def run(self):
        from seedcash.gui.screens.generate_seed_screens import (
            ToolsCalcFinalWordDoneScreen,
        )

        final_word = self.controller.storage.get_mnemonic_word(-1)
        generated_seed = self.controller.storage.get_seed_wallet()

        button_data = [self.FINISH, self.PASSPHRASE]

        selected_menu_num = ToolsCalcFinalWordDoneScreen(
            final_word=final_word,
            fingerprint=generated_seed.fingerprint,
            button_data=button_data,
        ).display()

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if button_data[selected_menu_num] == self.FINISH:
            from seedcash.views.view import MainMenuView

            # Discard the mnemonic and seed after generating the final word
            self.controller.storage.discard_mnemonic()
            self.controller.storage.discard_seed()

            return Destination(MainMenuView)

        elif button_data[selected_menu_num] == self.PASSPHRASE:
            from seedcash.views.wallet_views import SeedAddPassphraseView

            return Destination(
                SeedAddPassphraseView, view_args={"seed": generated_seed}
            )
