import logging
from gettext import gettext as _
from seedcash.gui.components import SeedCashIconsConstants
from seedcash.gui.screens import (
    RET_CODE__BACK_BUTTON,
    DireWarningScreen,
    WarningScreen,
    load_seed_screens,
)
from seedcash.gui.screens.screen import ButtonOption
from seedcash.views.view import (
    View,
    Destination,
    BackStackView,
    MainMenuView,
)


logger = logging.getLogger(__name__)


"""**************************************************
Seed Cash Updated Code
**************************************************"""


# Second Load Seed View for input
class SeedMnemonicEntryView(View):
    def __init__(self, cur_word_index: int = 0, is_calc_final_word: bool = False):
        super().__init__()
        # counter
        self.cur_word_index = cur_word_index
        # getting the index
        self.cur_word = self.controller.storage.get_mnemonic_word(cur_word_index)
        # for the generation of seed
        self.is_calc_final_word = is_calc_final_word
        # Save the view

    def run(self):
        ret = self.run_screen(
            load_seed_screens.SeedMnemonicEntryScreen,
            # TRANSLATOR_NOTE: Inserts the word number (e.g. "Seed Word #6")
            title=_("Seed Word #{}").format(
                self.cur_word_index + 1
            ),  # Human-readable 1-indexing!
            initial_letters=list(self.cur_word) if self.cur_word else ["a"],
            wordlist=self.controller.storage.get_wordlist,
        )

        if ret == RET_CODE__BACK_BUTTON:
            # remove the cur_word
            self.controller.storage.update_mnemonic(None, self.cur_word_index)

            if (
                self.cur_word_index == 0
                and self.controller.storage.mnemonic
                != [None] * self.controller.storage.mnemonic_length
            ):
                return Destination(SeedMnemonicDiscardView, skip_current_view=True)

            return Destination(BackStackView)

        # ret will be our new mnemonic word
        self.controller.storage.update_mnemonic(ret, self.cur_word_index)

        if (
            self.is_calc_final_word
            and self.cur_word_index == self.controller.storage.mnemonic_length - 2
        ):
            # Time to calculate the last word. User must decide how they want to specify
            # the last bits of entropy for the final word.
            from seedcash.views.generate_seed_views import (
                ToolsCalcFinalWordCoinFlipsView,
            )

            return Destination(ToolsCalcFinalWordCoinFlipsView)

        if (
            self.is_calc_final_word
            and self.cur_word_index == self.controller.storage.mnemonic_length - 1
        ):
            # Time to calculate the last word. User must either select a final word to
            # contribute entropy to the checksum word OR we assume 0 ("abandon").
            from seedcash.views.generate_seed_views import (
                ToolsCalcFinalWordShowFinalWordView,
            )

            return Destination(ToolsCalcFinalWordShowFinalWordView)

        if self.cur_word_index < (self.controller.storage.mnemonic_length - 1):
            return Destination(
                SeedMnemonicEntryView,
                view_args={
                    "cur_word_index": self.cur_word_index + 1,
                    "is_calc_final_word": self.is_calc_final_word,
                },
            )
        else:
            # Display the seed words for confirmation
            from seedcash.gui.screens.load_seed_screens import SeedCashSeedWordsScreen

            confirm = self.run_screen(
                SeedCashSeedWordsScreen,
                seed_words=self.controller.storage._mnemonic,
            )

            if confirm == "CONFIRM":
                try:
                    self.controller.storage.convert_mnemonic_to_seed()
                    self.controller.storage.create_wallet()

                except Exception as e:
                    for i in range(self.controller.storage.mnemonic_length):
                        self.controller.back_stack.pop()

                    return Destination(SeedMnemonicInvalidView)
                from seedcash.views.wallet_views import WalletFinalizeView

                return Destination(WalletFinalizeView)


# Third Possible Load Seed View if the user enters the wrong mnemonic
class SeedMnemonicInvalidView(View):
    EDIT = ButtonOption("Review & Edit")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def __init__(self):
        super().__init__()
        self.mnemonic: list[str] = self.controller.storage._mnemonic

    def run(self):
        button_data = [self.EDIT, self.DISCARD]
        selected_menu_num = self.run_screen(
            DireWarningScreen,
            title=_("Invalid Mnemonic!"),
            status_icon_name=SeedCashIconsConstants.ERROR,
            status_headline=None,
            text=_("Checksum failure; not a valid seed phrase."),
            show_back_button=False,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(
                SeedMnemonicEntryView,
                view_args={"cur_word_index": 0},
                skip_current_view=True,
            )

        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.storage.discard_mnemonic()
            return Destination(MainMenuView)


class SeedMnemonicDiscardView(View):
    EDIT = ButtonOption("Review & Edit")
    DISCARD = ButtonOption("Discard", button_label_color="red")

    def __init__(self):
        super().__init__()
        self.mnemonic: list[str] = self.controller.storage._mnemonic

    def run(self):
        button_data = [self.EDIT, self.DISCARD]
        selected_menu_num = self.run_screen(
            WarningScreen,
            title=_("Discard Mnemonic!"),
            status_icon_name=SeedCashIconsConstants.ERROR,
            status_headline=None,
            text=_("Are you sure you want to discard this mnemonic?"),
            show_back_button=False,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.EDIT:
            return Destination(
                SeedMnemonicEntryView,
                view_args={"cur_word_index": 0},
                skip_current_view=True,
            )

        elif button_data[selected_menu_num] == self.DISCARD:
            self.controller.storage.discard_mnemonic()
            return Destination(MainMenuView)
