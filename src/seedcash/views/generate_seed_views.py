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

        if (
            Settings.get_instance().get_value(SettingsConstants.SETTING__SEED_PROTOCOL) 
            == SettingsConstants.SEED_PROTOCOL__BIP39):
            self.CALCULATE_SEED = ButtonOption("Calculate Last Word")
            self.is_slip39 = False
        else:
            self.CALCULATE_SEED = ButtonOption("Custom Entropy Seed")
            self.is_slip39 = True

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
                SeedCashChooseWordsView, view_args=dict(is_calc_final_word=True, is_slip39=self.is_slip39)
            )
        elif button_data[selected_menu_num] == self.RANDOM_SEED:
            return Destination(
                SeedCashChooseWordsView, view_args=dict(is_random_seed=True, is_slip39=self.is_slip39)
            )

        return Destination(BackStackView)

class ShowWordsView(View):
    def run(self):
        from seedcash.gui.screens.load_seed_screens import SeedCashSeedWordsScreen

        confirm = self.run_screen(
            SeedCashSeedWordsScreen,
            seed_words=self.controller.storage.mnemonic,
        )

        if confirm == "CONFIRM":
            from seedcash.views.wallet_views import WalletFinalizeView
            self.controller.storage.convert_mnemonic_to_seed()
            self.controller.storage.create_wallet()
            return Destination(WalletFinalizeView)


class ToolsCalcFinalWordCoinFlipsView(View):
    def run(self):
        from seedcash.gui.screens.generate_seed_screens import ToolsCoinFlipEntryScreen

        total_bits = 11 - (self.controller.storage.mnemonic_length // 3)

        ret_val = ToolsCoinFlipEntryScreen(
            return_after_n_chars=total_bits,
        ).display()

        if ret_val == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        self.controller.storage.calculate_final_word(coin_flips=ret_val)
        return Destination(ToolsCalcFinalWordShowFinalWordView)


class ToolsCalcFinalWordShowFinalWordView(View):
    CONFIRM = ButtonOption("Confirm")

    def __init__(self):
        super().__init__()
        self.last_bits, self.checksum_bits = self.controller.storage.calculate_last_word_fields

    def run(self):
        from seedcash.gui.screens.generate_seed_screens import ToolsCalcFinalWordScreen

        button_data = [self.CONFIRM]

        selected_menu_num = self.run_screen(
            ToolsCalcFinalWordScreen,
            button_data=button_data,
            num_checksum_bits=self.controller.storage.mnemonic_length // 3,
            selected_final_bits=self.last_bits,
            checksum_bits=self.checksum_bits,
            actual_final_word=self.controller.storage.mnemonic[-1],
        )

        if button_data[selected_menu_num] == self.CONFIRM:
            return Destination(ShowWordsView)