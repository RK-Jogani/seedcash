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
)
from seedcash.models.settings_definition import SettingsConstants

import logging

logger = logging.getLogger(__name__)


# Final Possible Load Seed View
class SettingOptionsView(View):
    LANGUAGE = ButtonOption("Language")
    TEST_BUTTONS = ButtonOption("Test Buttons")
    TEST_CAMERA = ButtonOption("Test Camera")
    CAMERA_ROTATION = ButtonOption("Camera Rotation")

    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.seed

    def run(self):

        button_data = [
            self.LANGUAGE,
            self.TEST_BUTTONS,
            self.TEST_CAMERA,
            self.CAMERA_ROTATION,
        ]

        selected_menu_num = self.run_screen(
            setting_screens.SettingOptionsScreen,
            title="Settings",
            button_data=button_data,
        )
        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(MainMenuView)
        elif button_data[selected_menu_num] == self.LANGUAGE:
            return Destination(SettingLanguageView)
        elif button_data[selected_menu_num] == self.TEST_BUTTONS:
            return Destination(SettingTestButtons)
        elif button_data[selected_menu_num] == self.TEST_CAMERA:
            from seedcash.views.scan_view import ScanView

            return Destination(ScanView)
        elif button_data[selected_menu_num] == self.CAMERA_ROTATION:
            return Destination(CameraRotationOptionsView)


class SettingLanguageView(View):
    ENGLISH = ButtonOption("English")

    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.seed

    def run(self):

        button_data = [self.ENGLISH]

        selected_menu_num = self.run_screen(
            setting_screens.SettingOptionsScreen,
            title="Language",
            button_data=button_data,
        )
        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif button_data[selected_menu_num] == self.ENGLISH:
            return Destination(BackStackView)


class SettingTestButtons(View):
    def run(self):
        self.run_screen(setting_screens.SettingTestButtonsScreen)

        return Destination(SettingOptionsView)


class CameraRotationOptionsView(View):
    ROTATION_0 = ButtonOption("Rotation 0")
    ROTATION_90 = ButtonOption("Rotation 90")
    ROTATION_180 = ButtonOption("Rotation 180")
    ROTATION_270 = ButtonOption("Rotation 270")

    def __init__(self):
        super().__init__()
        self.seed = self.controller.storage.seed

    def run(self):

        button_data = [
            self.ROTATION_0,
            self.ROTATION_90,
            self.ROTATION_180,
            self.ROTATION_270,
        ]

        rotations = [0, 90, 180, 270]
        selected_btn = rotations.index(
            self.controller.settings.get_value(
                SettingsConstants.SETTING__CAMERA_ROTATION
            )
        )

        selected_menu_num = self.run_screen(
            setting_screens.SettingOptionsScreen,
            title="Camera Rotation",
            button_data=button_data,
            selected_button=selected_btn,
        )
        if selected_menu_num == RET_CODE__BACK_BUTTON:
            return Destination(BackStackView)
        elif button_data[selected_menu_num] == self.ROTATION_0:
            self.controller.settings.set_value(
                SettingsConstants.SETTING__CAMERA_ROTATION,
                SettingsConstants.CAMERA_ROTATION__0,
            )
            return Destination(BackStackView)
        elif button_data[selected_menu_num] == self.ROTATION_90:
            self.controller.settings.set_value(
                SettingsConstants.SETTING__CAMERA_ROTATION,
                SettingsConstants.CAMERA_ROTATION__90,
            )
            return Destination(BackStackView)
        elif button_data[selected_menu_num] == self.ROTATION_180:
            self.controller.settings.set_value(
                SettingsConstants.SETTING__CAMERA_ROTATION,
                SettingsConstants.CAMERA_ROTATION__180,
            )
            return Destination(BackStackView)
        elif button_data[selected_menu_num] == self.ROTATION_270:
            self.controller.settings.set_value(
                SettingsConstants.SETTING__CAMERA_ROTATION,
                SettingsConstants.CAMERA_ROTATION__270,
            )
            return Destination(BackStackView)
