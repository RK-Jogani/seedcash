import hashlib
import logging

from gettext import gettext as _
import time
from seedcash.gui.components import resize_image_to_fill
from seedcash.gui.screens import RET_CODE__BACK_BUTTON
from seedcash.gui.screens.screen import ButtonListScreen, ButtonOption
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
            from seedcash.views.wallet_views import WalletFinalizeView
            self.controller.storage.convert_mnemonic_to_seed()
            self.controller.storage.create_wallet()
            return Destination(WalletFinalizeView)

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