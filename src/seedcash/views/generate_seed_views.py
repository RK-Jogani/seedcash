import logging

from gettext import gettext as _
import random
import time
from seedcash.gui.components import SeedCashIconsConstants, resize_image_to_fill
from seedcash.gui.screens import RET_CODE__BACK_BUTTON
from seedcash.gui.screens.screen import ButtonOption, DireWarningScreen, SeedCashButtonListWithNav
from seedcash.views.view import (
    View,
    Destination,
    BackStackView,
)

logger = logging.getLogger(__name__)

"""**************************************************
Seed Cash Updated Code
**************************************************"""


"""****************************************************************************
    Image entropy Views
****************************************************************************"""
class ShowWordsView(View):
    def run(self):
        from seedcash.gui.screens.load_seed_screens import SeedCashSeedWordsScreen

        from seedcash.gui.screens.screen import WarningScreen
        self.run_screen(
            WarningScreen,
            show_back_button=False,
            title="",
            text="Exposing your Seed gives full control of your funds")

        confirm = self.run_screen(
            SeedCashSeedWordsScreen,
            seed_words=self.controller.storage.mnemonic,
        )

        if confirm == "CONFIRM":
            return Destination(SeedWordsBackupTestPromptView)

class ToolsImageEntropyLivePreviewView(View):
    """
    A fixed number of live preview frames are collected into a frame pool to provide an
    additional source of entropy. These frames provide VOLUME for the final seed but are
    not themselves individually assessed for entropy QUALITY. The quality heuristics are
    only applied to the final image capture.

    The preview pool enforces two rules:
    1.) A frame that is a single flat color is rejected (e.g. completely black, completely
    white, all just one shade of green).

    2.) A frame identical to any previously admitted frame is rejected (de-duplicated via
    sha256).

    The final image cannot be taken until the full pool has arrived.

    This mirrors the role that NIST SP 800-90B (sec. 4.2) assigns to continuous health
    tests: detect gross noise-source failure -- a sensor stuck on one value, a stalled
    or repeating camera -- without attempting to measure entropy.
    """

    def run(self):
        from seedcash.gui.screens.generate_seed_screens import ToolsImageEntropyLivePreviewScreen
        self.controller.image_entropy_preview_frames = None
        ret = self.run_screen(ToolsImageEntropyLivePreviewScreen)

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        # The live preview screen must return the required number of preview pool frames.
        # Do not proceed if there is any mismatch.
        if ret is None or len(ret) != ToolsImageEntropyLivePreviewScreen.PREVIEW_POOL_SIZE:
            num_frames = 0 if ret is None else len(ret)
            # TRANSLATOR_NOTE: Shown when the camera fails to collect enough frames for a new seed. "expected" and "actual" are the number of frames.
            raise Exception(_("Entropy collection failed. Expected {expected} preview frames, got {actual}").format(expected=ToolsImageEntropyLivePreviewScreen.PREVIEW_POOL_SIZE, actual=num_frames))

        self.controller.image_entropy_preview_frames = ret
        return Destination(ToolsImageEntropyFinalImageView)

class ToolsImageEntropyFinalImageView(View):
    def run(self):
        from PIL import Image
        from PIL.ImageOps import autocontrast
        from seedcash.gui.screens.generate_seed_screens import ToolsImageEntropyFinalImageScreen
        if not self.controller.image_entropy_final_image:
            from seedcash.hardware.camera import Camera
            # Take the final full-res image
            camera = Camera.get_instance()
            max_dim = max(self.canvas_width, self.canvas_height)

            # Final image will be at least 4x the number of pixels the screen can
            # actually display.
            camera.start_single_frame_mode(resolution=(2*max_dim, 2*max_dim))

            time.sleep(0.25)
            self.controller.image_entropy_final_image = camera.capture_frame()
            camera.stop_single_frame_mode()

        # Prep a copy of the image for display:
        #   * Boost the contrast for better presentation (but preserve the original pixels)
        #   * Resize it to fit the screen
        boosted_version = autocontrast(self.controller.image_entropy_final_image, cutoff=2)
        display_version = resize_image_to_fill(
            boosted_version,
            target_size_x=self.canvas_width,
            target_size_y=self.canvas_height,
            sampling_method=Image.Resampling.BICUBIC,
        )
        
        ret = self.run_screen(
            ToolsImageEntropyFinalImageScreen,
            final_image=display_version
        )

        if ret == RET_CODE__BACK_BUTTON:
            # Go back to live preview and reshoot
            self.controller.image_entropy_final_image = None
            return Destination(BackStackView)

        self.controller.build_mnemonic_images_entropy()
        return Destination(ShowWordsView)

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

class SeedWordsBackupTestPromptView(View):
    VERIFY = ButtonOption("Verify")
    SKIP = ButtonOption("Skip")

    def __init__(self):
        super().__init__()

    def run(self):
        button_data = [self.VERIFY, self.SKIP]
        
        from seedcash.gui.screens.generate_seed_screens import SeedWordsBackupTestPromptScreen
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