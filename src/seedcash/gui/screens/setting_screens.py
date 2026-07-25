import logging
from gettext import gettext as _
from dataclasses import dataclass
from PIL.ImageOps import autocontrast
import time
from seedcash.gui.components import (
    Button,
    Fonts,
    TextArea,
    GUIConstants,
    Icon,
    IconButton,
    FontAwesomeIconConstants,
    SeedCashIconsConstants,
)

from seedcash.hardware.camera import Camera
from seedcash.hardware.buttons import HardwareButtonsConstants
from .screen import BaseTopNavScreen

logger = logging.getLogger(__name__)


@dataclass
class SettingTestButtonsScreen(BaseTopNavScreen):
    def __post_init__(self):
        # TRANSLATOR_NOTE: Short for "Input/Output"; screen to make sure the buttons and camera are working properly
        self.title = _("I/O Test")
        self.show_back_button = False
        self.resolution = (96, 96)
        self.framerate = 10
        self.instructions_text = None
        super().__post_init__()

        # D-pad pictogram
        input_button_width = GUIConstants.BUTTON_HEIGHT + 2
        input_button_height = input_button_width + 2
        dpad_center_x = (
            GUIConstants.EDGE_PADDING
            + input_button_width
            + GUIConstants.COMPONENT_PADDING
        )
        dpad_center_y = int((self.canvas_height - input_button_height) / 2)

        self.joystick_click_button = IconButton(
            icon_name=FontAwesomeIconConstants.CIRCLE,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE - 6,
            width=input_button_width,
            height=input_button_height,
            screen_x=dpad_center_x,
            screen_y=dpad_center_y,
            outline_color=GUIConstants.ACCENT_COLOR,
        )
        self.components.append(self.joystick_click_button)

        self.joystick_up_button = IconButton(
            icon_name=SeedCashIconsConstants.CHEVRON_UP,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            width=input_button_width,
            height=input_button_height,
            screen_x=dpad_center_x,
            screen_y=dpad_center_y
            - input_button_height
            - GUIConstants.COMPONENT_PADDING,
            outline_color=GUIConstants.ACCENT_COLOR,
        )
        self.components.append(self.joystick_up_button)

        self.joystick_down_button = IconButton(
            icon_name=SeedCashIconsConstants.CHEVRON_DOWN,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            width=input_button_width,
            height=input_button_height,
            screen_x=dpad_center_x,
            screen_y=dpad_center_y
            + input_button_height
            + GUIConstants.COMPONENT_PADDING,
            outline_color=GUIConstants.ACCENT_COLOR,
        )
        self.components.append(self.joystick_down_button)

        self.joystick_left_button = IconButton(
            icon_name=SeedCashIconsConstants.CHEVRON_LEFT,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            width=input_button_width,
            height=input_button_height,
            screen_x=dpad_center_x
            - input_button_width
            - GUIConstants.COMPONENT_PADDING,
            screen_y=dpad_center_y,
            outline_color=GUIConstants.ACCENT_COLOR,
        )
        self.components.append(self.joystick_left_button)

        self.joystick_right_button = IconButton(
            icon_name=SeedCashIconsConstants.CHEVRON_RIGHT,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            width=input_button_width,
            height=input_button_height,
            screen_x=dpad_center_x
            + input_button_width
            + GUIConstants.COMPONENT_PADDING,
            screen_y=dpad_center_y,
            outline_color=GUIConstants.ACCENT_COLOR,
        )
        self.components.append(self.joystick_right_button)

        # Hardware keys UI
        font = Fonts.get_font(
            GUIConstants.BUTTON_FONT_NAME, GUIConstants.BUTTON_FONT_SIZE
        )
        (left, top, text_width, bottom) = font.getbbox(text=_("Clear"), anchor="ls")
        icon = Icon(
            icon_name=FontAwesomeIconConstants.CAMERA,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
        )
        key_button_width = (
            text_width + 2 * GUIConstants.COMPONENT_PADDING + GUIConstants.EDGE_PADDING
        )
        key_button_height = icon.height + int(1.5 * GUIConstants.COMPONENT_PADDING)
        key2_y = int(self.canvas_height / 2) - int(key_button_height / 2)

        self.key2_button = Button(
            # TRANSLATOR_NOTE: Blank the screen
            text=_("Clear"),  # Initialize with text to set vertical centering
            width=key_button_width,
            height=key_button_height,
            screen_x=self.canvas_width - key_button_width + GUIConstants.EDGE_PADDING,
            screen_y=key2_y,
            outline_color=GUIConstants.ACCENT_COLOR,
            is_scrollable_text=False,  # Text has to dynamically update, can't use scrollable Button
        )
        self.key2_button.text = " "  # but default state is empty
        self.components.append(self.key2_button)

        self.key1_button = IconButton(
            icon_name=FontAwesomeIconConstants.CAMERA,
            width=key_button_width,
            height=key_button_height,
            screen_x=self.canvas_width - key_button_width + GUIConstants.EDGE_PADDING,
            screen_y=key2_y - 3 * GUIConstants.COMPONENT_PADDING - key_button_height,
            outline_color=GUIConstants.ACCENT_COLOR,
        )
        self.components.append(self.key1_button)

        self.key3_button = Button(
            text=_("Exit"),
            width=key_button_width,
            height=key_button_height,
            screen_x=self.canvas_width - key_button_width + GUIConstants.EDGE_PADDING,
            screen_y=key2_y + 3 * GUIConstants.COMPONENT_PADDING + key_button_height,
            outline_color=GUIConstants.ACCENT_COLOR,
            is_scrollable_text=False,  # No help for l10n, but currently ScrollableTextLine interferes with the small button's left edge. (TODO:)
        )
        self.components.append(self.key3_button)

    def _run(self):
        cur_selected_button = self.key1_button
        msg_height = (
            GUIConstants.ICON_LARGE_BUTTON_SIZE + 2 * GUIConstants.COMPONENT_PADDING
        )
        camera_message = TextArea(
            text=_("Capturing image..."),
            font_size=GUIConstants.TOP_NAV_TITLE_FONT_SIZE,
            is_text_centered=True,
            height=msg_height,
            screen_y=int((self.canvas_height - msg_height) / 2),
        )
        while True:
            input = self.hw_inputs.wait_for(keys=HardwareButtonsConstants.ALL_KEYS)

            if input == HardwareButtonsConstants.KEY1:
                # Note that there are three distinct screen updates that happen at
                # different times, therefore we claim the `Renderer.lock` three separate
                # times.
                cur_selected_button = self.key1_button

                with self.renderer.lock:
                    # Render edges around message box
                    self.image_draw.rectangle(
                        (
                            -1,
                            int((self.canvas_height - msg_height) / 2) - 1,
                            self.canvas_width + 1,
                            int((self.canvas_height + msg_height) / 2) + 1,
                        ),
                        fill="black",
                        outline=GUIConstants.ACCENT_COLOR,
                        width=1,
                    )
                    cur_selected_button.is_selected = True
                    cur_selected_button.render()
                    camera_message.render()
                    self.renderer.show_image()

                # Snap a pic, render it as the background, re-render all onscreen elements
                camera = Camera.get_instance()
                try:
                    camera.start_single_frame_mode(
                        resolution=(self.canvas_width, self.canvas_height)
                    )

                    # Reset the button state
                    with self.renderer.lock:
                        cur_selected_button.is_selected = False
                        cur_selected_button.render()
                        self.renderer.show_image()

                    time.sleep(0.25)
                    background_frame = camera.capture_frame()
                    display_version = autocontrast(background_frame, cutoff=2)
                    with self.renderer.lock:
                        self.canvas.paste(display_version, (0, self.top_nav.height))
                        self.key2_button.text = _("Clear")
                        for component in self.components:
                            component.render()
                        self.renderer.show_image()
                finally:
                    camera.stop_single_frame_mode()

                continue

            elif input == HardwareButtonsConstants.KEY2:
                cur_selected_button = self.key2_button

                # Clear the background
                with self.renderer.lock:
                    cur_selected_button.is_selected = True
                    self._render()
                    self.renderer.show_image()

                    # And then re-render Key2 in its initial state
                    self.key2_button.text = " "
                    cur_selected_button.is_selected = False
                    cur_selected_button.render()
                    self.renderer.show_image()

                continue

            elif input == HardwareButtonsConstants.KEY3:
                # Exit
                cur_selected_button = self.key3_button
                cur_selected_button.is_selected = True
                with self.renderer.lock:
                    cur_selected_button.render()
                    self.renderer.show_image()
                    return

            elif input == HardwareButtonsConstants.KEY_PRESS:
                cur_selected_button = self.joystick_click_button

            elif input == HardwareButtonsConstants.KEY_UP:
                cur_selected_button = self.joystick_up_button

            elif input == HardwareButtonsConstants.KEY_DOWN:
                cur_selected_button = self.joystick_down_button

            elif input == HardwareButtonsConstants.KEY_LEFT:
                cur_selected_button = self.joystick_left_button

            elif input == HardwareButtonsConstants.KEY_RIGHT:
                cur_selected_button = self.joystick_right_button

            with self.renderer.lock:
                cur_selected_button.is_selected = True
                cur_selected_button.render()
                self.renderer.show_image()

            with self.renderer.lock:
                cur_selected_button.is_selected = False
                cur_selected_button.render()
                self.renderer.show_image()

            time.sleep(0.1)


class SettingDerivationPathScreen(BaseTopNavScreen):
    def __post_init__(self):
        # TRANSLATOR_NOTE: Short for "Derivation Path"; screen to set the derivation path for wallet generation
        self.title = _("Derivation Path")
        self.show_back_button = True
        super().__post_init__()

        self.derivation_btn = Button(
            text="m/44'/145'/0'",
            width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
            height=GUIConstants.BUTTON_HEIGHT,
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.top_nav.height + GUIConstants.COMPONENT_PADDING,
        )

        self.components.append(self.derivation_btn)

        self.confirm_btn = Button(
            text=_("Confirm"),
            width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
            height=GUIConstants.BUTTON_HEIGHT,
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.canvas_height
            - GUIConstants.EDGE_PADDING
            - GUIConstants.BUTTON_HEIGHT,
        )

        self.components.append(self.confirm_btn)

        self.selected_button = 2
        self.components[self.selected_button].is_selected = True

    def _run(self):
        while True:
            input = self.hw_inputs.wait_for(
                HardwareButtonsConstants.KEYS__LEFT_RIGHT_UP_DOWN
                + HardwareButtonsConstants.KEYS__ANYCLICK
            )

            if input in HardwareButtonsConstants.KEYS__ANYCLICK:
                return

            if input in [
                HardwareButtonsConstants.KEY_LEFT,
                HardwareButtonsConstants.KEY_RIGHT,
            ]:
                continue

            if input == HardwareButtonsConstants.KEY_UP:
                if not self.top_nav.is_selected:
                    self.components[self.selected_button].is_selected = False
                    self.components[self.selected_button].render()
                    self.top_nav.is_selected = True
                    self.top_nav.render_buttons()

            elif input == HardwareButtonsConstants.KEY_DOWN:
                if self.top_nav.is_selected:
                    self.top_nav.is_selected = False
                    self.top_nav.render_buttons()
                    self.components[self.selected_button].is_selected = True
                    self.components[self.selected_button].render()

            self.renderer.show_image()
