import random

from gettext import gettext as _
from seedcash.gui.components import SeedCashIconsConstants
from seedcash.gui.screens.screen import (
    RET_CODE__BACK_BUTTON,
    ButtonOption,
    SeedCashButtonListWithNav,
    DireWarningScreen,
)

from seedcash.views.view import (
    View,
    Destination,
    BackStackView
)

# Logger for this module
import logging
logger = logging.getLogger(__name__)

"""**************************************************
Seed Cash Updated Code
**************************************************"""

class GenerateSeedView(View):
    def __init__(self):
        super().__init__()
        self.RANDOM_SEED = ButtonOption("Random Seed")
        self.CALCULATE_SEED = ButtonOption("Calculate Last Word") 

    def run(self):
        
        button_data = [self.RANDOM_SEED, self.CALCULATE_SEED]

        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            button_data=button_data,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        if button_data[selected_menu_num] == self.RANDOM_SEED:
            from seedcash.views.view import ToolsImageEntropyLivePreviewView
            return Destination(ToolsImageEntropyLivePreviewView)
        elif button_data[selected_menu_num] == self.CALCULATE_SEED:
            from seedcash.views.load_seed_views import SeedMnemonicEntryView
            return Destination(SeedMnemonicEntryView, view_args={"is_calc_final_word": True})

class ToolsCalcFinalWordCoinFlipsView(View):
    def run(self):
        from seedcash.gui.screens.generate_seed_screens import ToolsCoinFlipEntryScreen

        total_bits = 11 - (self.controller.storage.mnemonic_length // 3)

        ret_val = ToolsCoinFlipEntryScreen(
            max_bits=total_bits,
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

class ShowWordsView(View):
    def run(self):
        from seedcash.gui.screens.load_seed_screens import SeedCashSeedWordsScreen

        confirm = self.run_screen(
            SeedCashSeedWordsScreen,
            seed_words=self.controller.storage.mnemonic,
        )

        if confirm == "CONFIRM":
            return Destination(SeedWordsBackupTestPromptView)

class SeedWordsBackupTestPromptView(View):
    VERIFY = ButtonOption("Verify")
    SKIP = ButtonOption("Skip")

    def __init__(self):
        super().__init__()

    def run(self):
        button_data = [self.VERIFY, self.SKIP]
        
        from seedcash.gui.screens.screen import SeedWordsBackupTestPromptScreen
        selected_menu_num = self.run_screen(
            SeedWordsBackupTestPromptScreen,
            button_data=button_data,
        )

        if button_data[selected_menu_num] == self.VERIFY:
            return Destination(SeedWordsBackupTestView)

        elif button_data[selected_menu_num] == self.SKIP:
            self.controller.storage.convert_mnemonic_to_seed()
            self.controller.storage.create_wallet()
            from seedcash.views.wallet_views import WalletFinalizeView
            return Destination(WalletFinalizeView)

class SeedWordsBackupTestView(View):
    def __init__(self, confirmed_list: list = None, cur_index: int = None, rand_seed: int = None):
        super().__init__()
        self.cur_index = cur_index
        self.rand_seed = rand_seed
        self.wordlist = self.controller.storage.get_wordlist
        self.mnemonic_list = self.controller.storage.mnemonic
        self.confirmed_list = confirmed_list
        if not self.confirmed_list:
            self.confirmed_list = []

    def run(self):
        
        if self.rand_seed is not None:
            random.seed(self.rand_seed + self.cur_index if self.cur_index is not None else 0)

        if self.cur_index is None:
            self.cur_index = int(random.random() * len(self.mnemonic_list))
            while self.cur_index in self.confirmed_list:
                self.cur_index = int(random.random() * len(self.mnemonic_list))

        real_word = ButtonOption(self.mnemonic_list[self.cur_index])
        fake_word1 = ButtonOption(self.wordlist[int(random.random() * 2047)])
        fake_word2 = ButtonOption(self.wordlist[int(random.random() * 2047)])
        fake_word3 = ButtonOption(self.wordlist[int(random.random() * 2047)])

        button_data = [real_word, fake_word1, fake_word2, fake_word3]
        random.shuffle(button_data)

        # TRANSLATOR_NOTE: Inserts the word number (e.g. "Verify Word #1")
        title = _("Verify Word #{}").format(self.cur_index + 1)
        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            title=title,
            show_back_button=False,
            button_data=button_data,
            is_bottom_list=True,
            is_button_text_centered=True,
        )

        
        if button_data[selected_menu_num] == real_word:
            self.confirmed_list.append(self.cur_index)
            if len(self.confirmed_list) == len(self.mnemonic_list):
                # All mnemonic words have been successfully verified.
                return Destination(SeedWordsBackupTestSuccessView)
            else:
                # Continue verifying remaining unverified words.
                return Destination(
                    SeedWordsBackupTestView,
                    view_args=dict(
                        confirmed_list=self.confirmed_list,
                    )
                )
        else:
            # Picked the WRONG WORD!
            return Destination(
                SeedWordsBackupTestMistakeView,
                view_args=dict(
                    cur_index=self.cur_index,
                    wrong_word=button_data[selected_menu_num].button_label,
                    confirmed_list=self.confirmed_list,
                )
            )

class SeedWordsBackupTestMistakeView(View):
    REVIEW = ButtonOption("Review seed words")
    RETRY = ButtonOption("Try again")

    def __init__(self, cur_index: int = None, wrong_word: str = None, confirmed_list: list[bool] = None):
        super().__init__()
        self.cur_index = cur_index
        self.wrong_word = wrong_word
        self.confirmed_list = confirmed_list


    def run(self):
        button_data = [self.REVIEW, self.RETRY]

        # TRANSLATOR_NOTE: Inserts the word number and the word (e.g. "Word #1 is not "apple"!")
        text = _("Word #{} is not \"{}\"!").format(self.cur_index + 1, self.wrong_word)

        # TRANSLATOR_NOTE: User selected the wrong word during the mnemonic backup test (e.g. incorrectly said the 5th word was "zoo")
        status_headline = _("Wrong Word!")

        selected_menu_num = self.run_screen(
            DireWarningScreen,
            title=_("Verification Error"),
            show_back_button=False,
            status_icon_name=SeedCashIconsConstants.ERROR,
            status_headline=status_headline,
            button_data=button_data,
            text=text,
        )

        if button_data[selected_menu_num] == self.REVIEW:
            return Destination(ShowWordsView)

        elif button_data[selected_menu_num] == self.RETRY:
            return Destination(
                SeedWordsBackupTestView,
                view_args=dict(
                    confirmed_list=self.confirmed_list,
                    cur_index=self.cur_index,
                )
            )

class SeedWordsBackupTestSuccessView(View):
    def __init__(self):
        super().__init__()

    def run(self):
        from seedcash.gui.screens.screen import LargeIconStatusScreen
        self.run_screen(
            LargeIconStatusScreen,
            title=_("Backup Verified"),
            show_back_button=False,
            status_headline=_("Success!"),
            text=_("All mnemonic backup words were successfully verified!"),
            button_data=[ButtonOption("OK")]
        )

        self.controller.storage.convert_mnemonic_to_seed()
        self.controller.storage.create_wallet()
        from seedcash.views.wallet_views import WalletFinalizeView
        return Destination(WalletFinalizeView)
