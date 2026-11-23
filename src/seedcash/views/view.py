import time
from dataclasses import dataclass
from gettext import gettext as _
from typing import Type

from seedcash.gui.components import (
    SeedCashIconsConstants,
    resize_image_to_fill,
)

from seedcash.gui.screens.screen import (
    RET_CODE__BACK_BUTTON,
    BaseScreen,
    ButtonOption,
    WarningScreen,
    ErrorScreen,
)
from seedcash.models.settings import Settings
from seedcash.models.settings_definition import SettingsConstants

import logging
logger = logging.getLogger(__name__)


class BackStackView:
    """
    Empty class that just signals to the Controller to pop the most recent View off
    the back_stack.
    """

    pass


"""
    Views contain the biz logic to handle discrete tasks, exactly analogous to a Flask
    request/response function or a Django View. Each page/screen displayed to the user
    should be implemented in its own View.

    In a web context, the View would prepare data for the html/css/js presentation
    templates. We have to implement our own presentation layer (implemented as `Screen`
    objects). For the sake of code cleanliness and separation of concerns, the View code
    should not know anything about pixel-level rendering.

    Sequences that require multiple pages/screens should be implemented as a series of
    separate Views. Exceptions can be made for complex interactive sequences, but in
    general, if your View is instantiating multiple Screens, you're probably putting too
    much functionality in that View.

    As with http requests, Views can receive input vars to inform their behavior. Views
    can also prepare the next set of vars to set up the next View that should be
    displayed (akin to Flask's `return redirect(url, param1=x, param2=y))`).

    Navigation guidance:
    "Next" - Continue to next step
    "Done" - End of flow, return to entry point (non-destructive)
    "OK/Close" - Exit current screen (non-destructive)
    "Cancel" - End task and return to entry point (destructive)
"""


class View:
    def _initialize(self):
        """
        Whether the View is a regular class initialized by __init__() or a dataclass
        initialized by __post_init__(), this method will be called to set up the View's
        instance variables.
        """
        # Import here to avoid circular imports
        from seedcash.controller import Controller
        from seedcash.gui import Renderer

        self.controller: Controller = Controller.get_instance()
        self.settings = Settings.get_instance()

        # TODO: Pull all rendering-related code out of Views and into gui.screens implementations
        self.renderer = Renderer.get_instance()
        self.canvas_width = self.renderer.canvas_width
        self.canvas_height = self.renderer.canvas_height

        self.screen = None

        self._redirect: "Destination" = None

    def __init__(self):
        self._initialize()

    def __post_init__(self):
        self._initialize()

    @property
    def has_redirect(self) -> bool:
        if not hasattr(self, "_redirect"):
            # Easy for a View to forget to call super().__init__()
            raise Exception(
                f"{self.__class__.__name__} did not call super().__init__()"
            )
        return self._redirect is not None

    def set_redirect(self, destination: "Destination"):
        """
        Enables early `__init__()` / `__post_init__()` logic to redirect away from the
        current View.

        Set a redirect Destination and then immediately `return` to exit `__init__()` or
        `__post_init__()`. When the `Destination.run()` is called, it will see the redirect
        and immediately return that new Destination to the Controller without running
        the View's `run()`.
        """
        # Always insure skip_current_view is set for a redirect
        destination.skip_current_view = True
        self._redirect = destination

    def get_redirect(self) -> "Destination":
        return self._redirect

    def run_screen(self, Screen_cls: Type[BaseScreen], **kwargs) -> int | str:
        """
        Instantiates the provided Screen_cls and runs its interactive display.
        Returns the user's input upon completion.
        """
        try:
            self.screen = Screen_cls(**kwargs)
            return self.screen.display()
        finally:
            self.screen = None
            screensaver = getattr(self.controller, "screensaver", None)
            if screensaver is not None:
                screensaver.last_screen = None

    def run(self, **kwargs) -> "Destination":
        raise Exception("Must implement in the child class")


@dataclass
class Destination:
    """
    Basic struct to pass back to the Controller to tell it which View the user should
    be presented with next.
    """

    View_cls: Type[View]  # The target View to route to
    view_args: dict = None  # The input args required to instantiate the target View
    skip_current_view: bool = (
        False  # The current View is just forwarding; omit current View from history
    )
    clear_history: bool = False  # Optionally clears the back_stack to prevent "back"

    def __repr__(self):
        if self.View_cls is None:
            out = "None"
        else:
            out = self.View_cls.__name__
        if self.view_args:
            out += f"(<{len(self.view_args)} route args>)"
        else:
            out += "()"
        if self.clear_history:
            out += f" | clear_history: {self.clear_history}"
        return out

    def _instantiate_view(self):
        if not self.view_args:
            # Can't unpack (**) None so we replace with an empty dict
            self.view_args = {}

        # Instantiate the `View_cls` with the `view_args` dict
        self.view = self.View_cls(**self.view_args)

    def _run_view(self):
        if self.view.has_redirect:
            return self.view.get_redirect()
        return self.view.run()

    def run(self):
        try:
            self._instantiate_view()
            return self._run_view()
        finally:
            # The Controller keeps the Destination for navigation history; release
            # the executed View instance so it does not retain screen or secret state.
            self.view = None

    def __eq__(self, obj):
        """
        Equality test IGNORES the skip_current_view and clear_history options
        """
        return (
            isinstance(obj, Destination)
            and obj.View_cls == self.View_cls
            and obj.view_args == self.view_args
        )

    def __ne__(self, obj):
        return not obj == self


#########################################################################################
#
# Root level Views don't have a sub-module home so they live at the top level here.
#
#########################################################################################


# First Main Menu View
class MainMenuView(View):
    LOAD_SEED = ButtonOption("Load seed", SeedCashIconsConstants.LOAD_SEED)
    GENERATE_SEED = ButtonOption("Generate seed", SeedCashIconsConstants.GENERATE_SEED)
    SEED_STORAGE = ButtonOption("Store seed", SeedCashIconsConstants.STORE_SEED)
    SETTINGS = ButtonOption("Settings", SeedCashIconsConstants.SETTINGS)

    def run(self):
        from seedcash.gui.screens.screen import MainMenuScreen

        button_data = [
            self.LOAD_SEED,
            self.GENERATE_SEED,
            self.SEED_STORAGE,
            self.SETTINGS,
        ]
        selected_menu_num = self.run_screen(
            MainMenuScreen,
            button_data=button_data,
        )

        button_data.append("Power Off")

        if button_data[selected_menu_num] == self.LOAD_SEED:
            self.controller.storage._is_generate = False
            return Destination(MainSeedView)

        elif button_data[selected_menu_num] == self.GENERATE_SEED:
            self.controller.storage._is_generate = True
            return Destination(MainSeedView)

        elif button_data[selected_menu_num] == self.SETTINGS:
            from seedcash.views.setting_views import SettingOptionsView

            return Destination(SettingOptionsView)

        elif button_data[selected_menu_num] == "Power Off":
            return Destination(PowerOffView)

class MainSeedView(View):
    BIP39 = ButtonOption("BIP39")
    SLIP39 = ButtonOption("SLIP39")
    SEEDCASHCARD = ButtonOption("SeedCash Card")
    SEEDQR = ButtonOption("SeedQR")

    def __init__(self):
        super().__init__()
        self.is_generate = self.controller.storage._is_generate

    def run(self):
        from seedcash.gui.screens.screen import SeedCashButtonListWithNav

        if self.is_generate:
            button_data = [
                self.BIP39,
                self.SLIP39,
            ]
        else:
            button_data = [
                self.BIP39,
                self.SLIP39,
                self.SEEDCASHCARD,
                self.SEEDQR,
            ]

        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            title="Backup Protocol",
            button_data=button_data,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(MainMenuView)
        
        if button_data[selected_menu_num] == self.BIP39:
            self.controller.switch_seed_protocol(SettingsConstants.SEED_PROTOCOL__BIP39)
            return Destination(SeedCashChooseWordsView)

        elif button_data[selected_menu_num] == self.SLIP39:
            self.controller.switch_seed_protocol(SettingsConstants.SEED_PROTOCOL__SLIP39)
            return Destination(SeedCashChooseWordsView)

        elif button_data[selected_menu_num] == self.SEEDCASHCARD:
            return 

        elif button_data[selected_menu_num] == self.SEEDQR:
            from seedcash.views.scan_view import ScanSeedQRView
            return Destination(ScanSeedQRView)

# First Load Seed View
class SeedCashChooseWordsView(View):
    def __init__(self):
        super().__init__()

        self.buttons_values = self.controller.settings.get_instance().get_value(
            SettingsConstants.SETTING__CHOOSE_WORDS
        )

        self.is_slip39 = self.controller.settings.get_instance().get_value(
            SettingsConstants.SETTING__SEED_PROTOCOL
        ) == SettingsConstants.SEED_PROTOCOL__SLIP39

        self.is_generate = self.controller.storage._is_generate

        self.buttons_data = [
            ButtonOption(f"{num} Words") for num in self.buttons_values
        ]
        
    def run(self):
        
        from seedcash.gui.screens.screen import SeedCashButtonListWithNav
        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            button_data=self.buttons_data,
        )

        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)

        selected_menu_num = int(self.buttons_values[selected_menu_num])
        self.controller.storage.set_mnemonic_length(selected_menu_num)

        if self.is_generate:
            if self.is_slip39:
                from seedcash.views.generate_slip_views import GenerateSlipSeedView
                return Destination(GenerateSlipSeedView)
            else:
                from seedcash.views.generate_seed_views import GenerateSeedView
                return Destination(GenerateSeedView)
        else:
            if self.is_slip39:
                from seedcash.views.load_slip_views import SlipMnemonicEntryView
                return Destination(SlipMnemonicEntryView)
            else:
                from seedcash.views.load_seed_views import SeedMnemonicEntryView
                return Destination(SeedMnemonicEntryView, view_args={"cur_word_index": 0})       

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
        from seedcash.gui.screens.screen import ToolsImageEntropyLivePreviewScreen
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
    def __init__(self):
        super().__init__()
        self.is_slip39 = self.controller.settings.get_instance().get_value(
            SettingsConstants.SETTING__SEED_PROTOCOL
        ) == SettingsConstants.SEED_PROTOCOL__SLIP39

    def run(self):
        from PIL import Image
        from PIL.ImageOps import autocontrast
        from seedcash.gui.screens.screen import ToolsImageEntropyFinalImageScreen
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

        if self.is_slip39:
            from seedcash.views.generate_slip_views import SeedSlipBitsView
            return Destination(SeedSlipBitsView)

        from seedcash.views.generate_seed_views import ShowWordsView
        return Destination(ShowWordsView)

class PowerOffView(View):
    def __init__(self):
        super().__init__()

    def run(self):
        from seedcash.gui.screens.screen import PowerOffScreen

        ret = self.run_screen(PowerOffScreen)

        if ret == RET_CODE__BACK_BUTTON:
            return Destination(MainMenuView, clear_history=True)

@dataclass
class NotYetImplementedView(View):
    """
    Temporary View to use during dev.
    """

    text: str = "This is still on our to-do list!"

    def run(self):
        self.run_screen(
            WarningScreen,
            title=_("Work In Progress"),
            status_headline=_("Not Yet Implemented"),
            text=self.text,
            button_data=[ButtonOption("Back to Main Menu")],
        )

        # we should return to the backstack view
        return Destination(BackStackView)

@dataclass
class ErrorView(View):
    title: str = "Error"
    show_back_button: bool = True
    status_icon_name: str = SeedCashIconsConstants.ERROR
    status_headline: str = None
    text: str = None
    button_text: str = None
    next_destination: Destination = None

    def run(self):
        self.run_screen(
            ErrorScreen,
            title=self.title,
            status_icon_name=self.status_icon_name,
            status_headline=self.status_headline,
            text=self.text,
            button_data=[ButtonOption(self.button_text)],
            show_back_button=self.show_back_button,
        )
        return (
            self.next_destination
            if self.next_destination
            else Destination(MainMenuView, clear_history=True)
        )

@dataclass
class UnhandledExceptionView(View):
    error: list[str]

    def run(self):
        self.run_screen(
            ErrorScreen,
            title=_("System Error"),
            status_headline=self.error[0],
            text=self.error[1] + "\n" + self.error[2],
            allow_text_overflow=True,  # Fit what we can, let the rest go off the edges
        )

        return Destination(MainMenuView, clear_history=True)
