from seedcash.views.scan_view import TestCamera
from seedcash.views.view import (
    MainMenuView,
    View,
    Destination,
    BackStackView,
    RET_CODE__BACK_BUTTON,
)
from seedcash.gui.screens import setting_screens
from seedcash.gui.screens.screen import (
    ButtonOption,
    SeedCashButtonListWithNav,
)
from seedcash.models.settings_definition import SettingsConstants

import logging

logger = logging.getLogger(__name__)


# Final Possible Load Seed View
class SettingOptionsView(View):
    LANGUAGE = ButtonOption("Language")
    DERIVATION_PATH = ButtonOption("Derivation Path")
    TEST_BUTTONS = ButtonOption("Test Buttons")
    TEST_CAMERA = ButtonOption("Test Camera")
    CAMERA_ROTATION = ButtonOption("Camera Rotation")
    QR_BRIGHTNESS = ButtonOption("QR Brightness")

    def __init__(self):
        super().__init__()

    def run(self):

        button_data = [
            self.LANGUAGE,
            self.DERIVATION_PATH,
            self.TEST_BUTTONS,
            self.TEST_CAMERA,
            self.CAMERA_ROTATION,
            self.QR_BRIGHTNESS,
        ]

        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            title="Settings",
            button_data=button_data,
        )
        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(MainMenuView)
        elif button_data[selected_menu_num] == self.LANGUAGE:
            return Destination(SettingLanguageView)
        elif button_data[selected_menu_num] == self.DERIVATION_PATH:
            return Destination(SettingDerivationPathView)
        elif button_data[selected_menu_num] == self.TEST_BUTTONS:
            return Destination(SettingTestButtons)
        elif button_data[selected_menu_num] == self.TEST_CAMERA:
            return Destination(TestCamera)
        elif button_data[selected_menu_num] == self.CAMERA_ROTATION:
            return Destination(CameraRotationOptionsView)
        elif button_data[selected_menu_num] == self.QR_BRIGHTNESS:
            return Destination(SettingQRBrightnessView)


class SettingLanguageView(View):
    def __init__(self):
        super().__init__()

        # get all available languages
        self.available_languages = [
            lang[0] for lang in SettingsConstants.ALL_WORDLIST_LANGUAGES
        ]

        # Create button options for each available language
        self.language_buttons = [
            ButtonOption(lang[1]) for lang in SettingsConstants.ALL_WORDLIST_LANGUAGES
        ]

    def run(self):

        button_data = self.language_buttons

        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            title="Language",
            button_data=button_data,
        )
        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif button_data[selected_menu_num] in self.language_buttons:
            selected_language = self.available_languages[selected_menu_num]
            self.controller.settings.set_value(
                SettingsConstants.SETTING__WORDLIST_LANGUAGE, selected_language
            )
            logger.info(f"Language set to: {selected_language}")
            return Destination(BackStackView)

class SettingDerivationPathView(View):
    def __init__(self):
        super().__init__()

    def run(self):

        from seedcash.gui.screens.setting_screens import SettingDerivationPathScreen

        selected_menu_num = self.run_screen(
            SettingDerivationPathScreen,
            title="Derivation Path",
        )

        return Destination(BackStackView)


class SettingTestButtons(View):
    def run(self):
        self.run_screen(setting_screens.SettingTestButtonsScreen)

        return Destination(SettingOptionsView)


class CameraRotationOptionsView(View):
    def __init__(self):
        super().__init__()

        # Get Button Options for Camera Rotation
        self.camera_rotations = [
            ButtonOption(rotation[1])
            for rotation in SettingsConstants.ALL_CAMERA_ROTATIONS
        ]

    def run(self):

        button_data = self.camera_rotations
        selected_btn = [0, 90, 180, 270].index(
            self.controller.settings.get_value(
                SettingsConstants.SETTING__CAMERA_ROTATION
            )
        )

        selected_menu_num = self.run_screen(
            SeedCashButtonListWithNav,
            title="Camera Rotation",
            button_data=button_data,
            selected_button=selected_btn,
        )
        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif button_data[selected_menu_num] in self.camera_rotations:
            selected_rotation = SettingsConstants.ALL_CAMERA_ROTATIONS[
                selected_menu_num
            ][0]
            self.controller.settings.set_value(
                SettingsConstants.SETTING__CAMERA_ROTATION, selected_rotation
            )
            return Destination(BackStackView)


class SettingQRBrightnessView(View):
    def __init__(self):
        super().__init__()

    def run(self):
        from seedcash.gui.screens.screen import QRDisplayScreen
        from seedcash.models.encode_qr import GenericStaticQrEncoder
        from seedcash.models.threads import ThreadsafeCounter

        qr_encoder = GenericStaticQrEncoder(data="seedcash brightness test")
        
        current_brightness = self.controller.settings.get_value(SettingsConstants.SETTING__QR_BRIGHTNESS)
        if current_brightness is None:
            current_brightness = 255
            
        brightness_counter = ThreadsafeCounter(initial_value=int(current_brightness))
        
        self.run_screen(QRDisplayScreen, qr_encoder=qr_encoder, qr_brightness=brightness_counter)
        
        # Save any brightness adjustments made by the user
        self.controller.settings.set_value(SettingsConstants.SETTING__QR_BRIGHTNESS, brightness_counter.cur_count)
        
        return Destination(BackStackView)
