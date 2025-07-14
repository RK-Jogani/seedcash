import logging

from gettext import gettext as _

from seedcash.gui.components import SeedCashIconsConstants
from seedcash.gui.screens import RET_CODE__BACK_BUTTON
from seedcash.gui.screens.screen import ButtonOption
from seedcash.models.seed import Seed
from seedcash.views.view import (
    View,
    Destination,
    BackStackView,
)


logger = logging.getLogger(__name__)

"""**************************************************
Seed Cash Updated Code
**************************************************"""


# First Generate Seed View
class SeedCashGenerateSeedView(View):
    BACK = ButtonOption("BACK", SeedCashIconsConstants.BACK)
    NEXT = ButtonOption("NEXT", SeedCashIconsConstants.NEXT)
    label_text: str = (
        "Enter your mnemonic seed word by word and passphrase.\n Remember that Seedcash only supports 12 seed words."
    )

    def run(self):
        from seedcash.gui.screens.generate_seed_screens import (
            SeedCashGenerateSeedScreen,
        )

        button_data = [self.NEXT, self.BACK]

        selected_menu_num = self.run_screen(
            SeedCashGenerateSeedScreen,
        )

        if button_data[selected_menu_num] == self.BACK:
            return Destination(BackStackView)

        if button_data[selected_menu_num] == self.NEXT:
            from seedcash.views.load_seed_views import SeedMnemonicEntryView

            return Destination(
                SeedMnemonicEntryView, view_args=dict(is_calc_final_word=True)
            )

        return Destination(BackStackView)


class ToolsCalcFinalWordCoinFlipsView(View):
    def run(self):
        from seedcash.gui.screens.generate_seed_screens import ToolsCoinFlipEntryScreen

        mnemonic_length = len(self.controller.storage._mnemonic)

        if mnemonic_length == 12:
            total_flips = 7
        else:
            total_flips = 3

        ret_val = ToolsCoinFlipEntryScreen(
            return_after_n_chars=total_flips,
        ).display()

        if ret_val == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        else:
            return Destination(
                ToolsCalcFinalWordShowFinalWordView, view_args=dict(coin_flips=ret_val)
            )


class ToolsCalcFinalWordShowFinalWordView(View):
    NEXT = ButtonOption("Next")

    def __init__(self, coin_flips: str = None):
        super().__init__()
        # Construct the actual final word. The user's selected_final_word
        from seedcash.models import btc_functions as bf

        wordlist = Seed.get_wordlist()
        # Prep the user's selected word / coin flips and the actual final word for
        # the display.
        if coin_flips:
            self.selected_final_word = None
            self.selected_final_bits = coin_flips

        if coin_flips:
            # fill the last bits (what will eventually be the checksum) with zeros
            final_mnemonic = bf.get_mnemonic(
                self.controller.storage._mnemonic[:-1], coin_flips
            )

        # Update our pending mnemonic with the real final word
        self.controller.storage.update_mnemonic(final_mnemonic[-1], -1)

        mnemonic = self.controller.storage._mnemonic
        mnemonic_length = len(mnemonic)

        # And grab the actual final word's checksum bits
        self.actual_final_word = self.controller.storage._mnemonic[-1]
        num_checksum_bits = 4 if mnemonic_length == 12 else 8
        self.checksum_bits = format(wordlist.index(self.actual_final_word), "011b")[
            -num_checksum_bits:
        ]

    def run(self):
        from seedcash.gui.screens.generate_seed_screens import ToolsCalcFinalWordScreen

        button_data = [self.NEXT]

        # TRANSLATOR_NOTE: label to calculate the last word of a BIP-39 mnemonic seed phrase
        title = _("Final Word Calc")

        selected_menu_num = self.run_screen(
            ToolsCalcFinalWordScreen,
            button_data=button_data,
            selected_final_word=self.selected_final_word,
            selected_final_bits=self.selected_final_bits,
            checksum_bits=self.checksum_bits,
            actual_final_word=self.actual_final_word,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        elif button_data[selected_menu_num] == self.NEXT:
            return Destination(ToolsCalcFinalWordDoneView)


class ToolsCalcFinalWordDoneView(View):
    LOAD = ButtonOption("Load seed")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def run(self):
        from seedcash.gui.screens.generate_seed_screens import (
            ToolsCalcFinalWordDoneScreen,
        )

        final_word = self.controller.storage.get_mnemonic_word(-1)

        button_data = [self.LOAD, self.DISCARD]

        selected_menu_num = ToolsCalcFinalWordDoneScreen(
            final_word=final_word,
            fingerprint=self.controller.storage.get_fingerprint_mnemonic(),
            button_data=button_data,
        ).display()

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if button_data[selected_menu_num] == self.LOAD:
            self.controller.storage.convert_mnemonic_to_seed()
            from seedcash.views.load_seed_views import SeedFinalizeView

            return Destination(SeedFinalizeView)

        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.storage.discard_mnemonic()
            from seedcash.views.view import MainMenuView

            return Destination(MainMenuView)
