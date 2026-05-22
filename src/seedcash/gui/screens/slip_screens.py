import logging
import math
from seedcash.gui.components import (
    Button,
    GUIConstants,
    IconButton,
    IconTextLine,
    SeedCashIconsConstants,
    FontAwesomeIconConstants,
    TextArea,
)

from seedcash.models.slip39 import Slip39 as sp
from seedcash.gui.keyboard import TextEntryDisplay
from seedcash.gui.screens.screen import (
    RET_CODE__BACK_BUTTON,
    BaseTopNavScreen,
    BaseScreen,
    SeedCashButtonListWithNav,
)
from seedcash.hardware.buttons import HardwareButtonsConstants
from dataclasses import dataclass
from gettext import gettext as _
from PIL import Image, ImageDraw
from seedcash.models import visual_hash as vh
from seedcash.models.scheme import Scheme

logger = logging.getLogger(__name__)


@dataclass
class SlipEntryScreen(BaseTopNavScreen):
    num_words: int = 20

    def __post_init__(self):
        self.show_back_button = True
        self.title = _("Entropy Bits")
        super().__post_init__()

        if self.num_words == 20:
            self.bits = 128
        elif self.num_words == 33:
            self.bits = 256
        else:
            raise ValueError("Unsupported number of words for Slip39 seed phrase.")

        # Current entered bits
        self.current_bits = ""

        # Total number of screens
        self.total_screens = self.bits // 16
        # Initialize the current screen
        self.current_screen = 1

        # Is last screen
        self.is_last_screen = self.current_screen == self.total_screens

        # cursor position for text entry
        self.cursor_position = 0

        self.text_entry_display_y = (
            self.top_nav.height + 3 * GUIConstants.COMPONENT_PADDING
        )
        self.text_entry_display_height = 30

        # Add text display for the entered bits
        self.text_entry_display = TextEntryDisplay(
            canvas=self.renderer.canvas,
            rect=(
                GUIConstants.EDGE_PADDING,
                self.text_entry_display_y,
                self.canvas_width - GUIConstants.EDGE_PADDING,
                self.text_entry_display_y + self.text_entry_display_height,
            ),
            cursor_mode=TextEntryDisplay.CURSOR_MODE__BAR,
            is_centered=False,
            cur_text=self.current_bits,
        )

        self._custom_keyboard()
        self._dynamic_title()

        self.selected_button = 1  # Start with first button selected
        self.components[self.selected_button].is_selected = True

    def _custom_keyboard(self):
        btns_y = (
            self.text_entry_display_y
            + self.text_entry_display_height
            + 2 * GUIConstants.COMPONENT_PADDING
        )

        key_size = int(3 / 2 * GUIConstants.BUTTON_HEIGHT)
        special_key_size = 3 * GUIConstants.BUTTON_HEIGHT

        # 0 and 1 buttons
        self.key_0 = Button(
            text="0",
            is_text_centered=True,
            font_name=GUIConstants.BUTTON_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 8,
            screen_x=2 * GUIConstants.EDGE_PADDING,
            screen_y=btns_y,
            width=(key_size),
            height=key_size,
            is_selected=False,
        )

        self.key_1 = Button(
            text="1",
            is_text_centered=True,
            font_name=GUIConstants.BUTTON_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 8,
            screen_x=3 * GUIConstants.EDGE_PADDING + key_size,
            screen_y=btns_y,
            width=(key_size),
            height=key_size,
            is_selected=False,
        )

        # Create button for dice
        self.dice_button = IconButton(
            icon_name=FontAwesomeIconConstants.DICE,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE + 4,
            screen_x=4 * GUIConstants.EDGE_PADDING + 2 * key_size,
            screen_y=btns_y,
            width=(special_key_size),
            height=(key_size),
            is_text_centered=True,
            is_selected=False,
        )

        # special keys keyboard on second row

        # left cursor button
        left_cursor_btn = IconButton(
            icon_name=SeedCashIconsConstants.CHEVRON_LEFT,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            screen_x=2 * GUIConstants.EDGE_PADDING,
            screen_y=btns_y + key_size + GUIConstants.COMPONENT_PADDING,
            width=(key_size),
            height=(key_size),
            is_selected=False,
        )

        # right cursor button
        right_cursor_btn = IconButton(
            icon_name=SeedCashIconsConstants.CHEVRON_RIGHT,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            screen_x=3 * GUIConstants.EDGE_PADDING + key_size,
            screen_y=btns_y + key_size + GUIConstants.COMPONENT_PADDING,
            width=(key_size),
            height=(key_size),
            is_selected=False,
        )

        # create backspace button
        backspace_btn = IconButton(
            icon_name=SeedCashIconsConstants.DELETE,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE + 4,
            screen_x=4 * GUIConstants.EDGE_PADDING + 2 * key_size,
            screen_y=btns_y + key_size + GUIConstants.COMPONENT_PADDING,
            width=(special_key_size),
            height=key_size,
            is_selected=False,
        )

        self.components.append(self.key_0)
        self.components.append(self.key_1)
        self.components.append(self.dice_button)
        self.components.append(left_cursor_btn)
        self.components.append(right_cursor_btn)
        self.components.append(backspace_btn)

    def _dynamic_title(self):
        dynamic_title_text = _(f"{len(self.current_bits)}/{self.bits}")
        self.dynamic_title = IconTextLine(
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=GUIConstants.TOP_NAV_HEIGHT
            - int(5 / 2 * GUIConstants.COMPONENT_PADDING),
            height=GUIConstants.TOP_NAV_HEIGHT,
            icon_size=GUIConstants.ICON_FONT_SIZE + 4,
            value_text=dynamic_title_text,
            is_text_centered=True,
            font_name=GUIConstants.TOP_NAV_TITLE_FONT_NAME,
            font_size=GUIConstants.TOP_NAV_TITLE_FONT_SIZE,
        )
        self.components.append(self.dynamic_title)

    def _render(self):
        super()._render()
        self.text_entry_display.render(self.current_bits, self.cursor_position)

        for component in self.components:
            component.render()

        self.renderer.show_image()

    def _run(self):
        while True:
            input = self.hw_inputs.wait_for(
                [
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT,
                    HardwareButtonsConstants.KEY_UP,
                    HardwareButtonsConstants.KEY_DOWN,
                ]
                + HardwareButtonsConstants.KEYS__ANYCLICK,
            )

            with self.renderer.lock:

                if input == HardwareButtonsConstants.KEY_LEFT:
                    if self.selected_button > 1:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button -= 1
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()
                    else:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.top_nav.is_selected = True
                        self.top_nav.render_buttons()

                elif input == HardwareButtonsConstants.KEY_RIGHT:
                    if self.top_nav.is_selected:
                        self.top_nav.is_selected = False
                        self.top_nav.render_buttons()
                        self.selected_button = 1
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()
                    elif self.selected_button < 6:
                        logger.info(
                            f"Selected button before right: {self.selected_button}"
                        )
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button += 1
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()

                elif input == HardwareButtonsConstants.KEY_UP:
                    if self.selected_button in [1, 2, 3]:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.top_nav.is_selected = True
                        self.top_nav.render_buttons()
                    elif self.selected_button in [4, 5, 6]:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button -= 3
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()

                elif input == HardwareButtonsConstants.KEY_DOWN:
                    if self.top_nav.is_selected:
                        self.top_nav.is_selected = False
                        self.top_nav.render_buttons()
                        self.selected_button = 1
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()
                    elif self.selected_button in [1, 2, 3]:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button += 3
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()

                elif input in HardwareButtonsConstants.KEYS__ANYCLICK:
                    if self.top_nav.is_selected:
                        if input == HardwareButtonsConstants.KEY_PRESS:
                            return RET_CODE__BACK_BUTTON
                    else:
                        if self.selected_button == 1:  # Key 0
                            if len(self.current_bits) < self.bits:
                                self.current_bits = (
                                    self.current_bits[: self.cursor_position]
                                    + "0"
                                    + self.current_bits[self.cursor_position :]
                                )
                                self.cursor_position += 1
                        elif self.selected_button == 2:  # Key 1
                            if len(self.current_bits) < self.bits:
                                self.current_bits = (
                                    self.current_bits[: self.cursor_position]
                                    + "1"
                                    + self.current_bits[self.cursor_position :]
                                )
                                self.cursor_position += 1
                        elif self.selected_button == 3:  # Dice button
                            # random bits
                            self.current_bits = sp.get_random_bits_for_slip(
                                self.num_words
                            )
                            pass
                        elif self.selected_button == 4:  # Left cursor
                            if self.cursor_position > 0:
                                self.cursor_position -= 1
                        elif self.selected_button == 5:  # Right cursor
                            if self.cursor_position < len(self.current_bits):
                                self.cursor_position += 1
                        elif self.selected_button == 6:  # Backspace
                            if self.cursor_position > 0:
                                self.current_bits = (
                                    self.current_bits[: self.cursor_position - 1]
                                    + self.current_bits[self.cursor_position :]
                                )
                                self.cursor_position -= 1
                        # Check if we are done
                        if len(self.current_bits) == self.bits:
                            return self.current_bits

                self._dynamic_title()
                self._render()
                self.renderer.show_image()


@dataclass
class SlipBitsScreen(BaseScreen):
    bits: str = ""

    def __post_init__(self):
        super().__post_init__()

        if not self.bits:
            self.bits = ""

        self.bits_length = len(self.bits)
        self.current_page = 0
        self.bits_per_page = 64  # 4 buttons × 16 bits per button
        self.total_pages = (
            self.bits_length + self.bits_per_page - 1
        ) // self.bits_per_page

        # Calculate layout for bit display
        self.bit_height = GUIConstants.BUTTON_HEIGHT

        # Position bits below the top navigation
        self.bit_y = 4 * GUIConstants.COMPONENT_PADDING
        self.bit_x = 2 * GUIConstants.COMPONENT_PADDING
        self.bit_width = self.canvas_width - 4 * GUIConstants.COMPONENT_PADDING

        # Position for navigation buttons
        self.nav_buttons_y = (
            self.canvas_height - GUIConstants.BUTTON_HEIGHT - GUIConstants.EDGE_PADDING
        )

        # Create initial components
        self._create_components()

        # Start with back button selected
        self.selected_button = 0
        self.components[self.selected_button].is_selected = True

    def _create_components(self):
        """Create components for displaying seed words and navigation"""
        self.components.clear()

        # Add back button to return to the previous screen
        self.back_button = IconButton(
            icon_name=SeedCashIconsConstants.BACK,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.nav_buttons_y,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            is_text_centered=False,
            is_selected=False,
        )

        # Add next/confirm button
        next_icon = (
            SeedCashIconsConstants.CHECK
            if self.current_page == self.total_pages - 1
            else SeedCashIconsConstants.CHEVRON_RIGHT
        )

        self.next_button = IconButton(
            icon_name=next_icon,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            screen_x=self.canvas_width
            - GUIConstants.TOP_NAV_BUTTON_SIZE
            - GUIConstants.EDGE_PADDING,
            screen_y=self.nav_buttons_y,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            is_selected=False,
        )
        self.components.append(self.next_button)

        if self.current_page > 0:
            self.components.append(self.back_button)

        # Add bits for current page as non-selectable buttons (16 bits per button)
        start_index = self.current_page * self.bits_per_page
        end_index = min(start_index + self.bits_per_page, self.bits_length)

        # Group bits into chunks of 16
        bits_chunk = self.bits[start_index:end_index]
        button_count = 0

        for i in range(0, len(bits_chunk), 16):
            # Get 16 bits for this button
            sixteen_bits = bits_chunk[i : i + 16]

            # Add spacing every 4 bits for readability (e.g., "0000 1111 0101 1010")
            formatted_bits = " ".join(
                [sixteen_bits[j : j + 4] for j in range(0, len(sixteen_bits), 4)]
            )

            bit_y_pos = self.bit_y + (button_count * (self.bit_height))

            button = Button(
                text=formatted_bits,
                is_text_centered=True,
                font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
                font_size=GUIConstants.BODY_FONT_SIZE,
                screen_x=self.bit_x,
                screen_y=bit_y_pos,
                width=self.bit_width,
                height=self.bit_height + 2 * GUIConstants.COMPONENT_PADDING,
                is_selected=False,
                background_color=GUIConstants.BUTTON_BACKGROUND_COLOR,
                font_color=GUIConstants.BUTTON_FONT_COLOR,
            )
            self.components.append(button)
            button_count += 1

    def _render(self):
        """Render the screen with seed words"""
        super()._render()

        # Render all components
        for component in self.components:
            component.render()

        self.renderer.show_image()

    def _run(self):
        self._render()  # Initial render
        while True:
            ret = self._run_callback()
            if ret is not None:
                logging.info("Exiting SeedCashSeedWordsScreen due to _run_callback")
                return ret

            user_input = self.hw_inputs.wait_for(
                [
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT,
                ]
                + HardwareButtonsConstants.KEYS__ANYCLICK
            )

            with self.renderer.lock:
                if self.current_page == 0:  # select the next button
                    self.components[self.selected_button].is_selected = False
                    self.components[self.selected_button].render()
                    self.selected_button = 0
                    self.components[self.selected_button].is_selected = True
                    self.components[self.selected_button].render()

                    if user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                        self.current_page += 1
                        self._create_components()
                        # Keep selection on next button
                        self.selected_button = 0
                        self.components[self.selected_button].is_selected = True
                        self._render()

                else:
                    if user_input == HardwareButtonsConstants.KEY_LEFT:
                        # Move selection to back button
                        if self.selected_button == 0:
                            self.components[self.selected_button].is_selected = False
                            self.components[self.selected_button].render()
                            self.selected_button = 1
                            self.components[self.selected_button].is_selected = True
                            self.components[self.selected_button].render()

                    elif user_input == HardwareButtonsConstants.KEY_RIGHT:
                        # Move selection to next button
                        if self.selected_button == 1:
                            self.components[self.selected_button].is_selected = False
                            self.components[self.selected_button].render()
                            self.selected_button = 0
                            self.components[self.selected_button].is_selected = True
                            self.components[self.selected_button].render()
                    elif user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                        if self.selected_button == 1:  # Back button
                            if self.current_page > 1:
                                # Go back to previous page
                                self.current_page -= 1
                                self._create_components()
                                # Keep selection on back button
                                self.selected_button = 1
                                self.components[self.selected_button].is_selected = True
                                self._render()
                            else:
                                self.current_page = 0
                                self._create_components()
                                # Keep the selection on the next button
                                self.selected_button = 0
                                self.components[self.selected_button].is_selected = True
                                self._render()
                        elif self.selected_button == 0:  # Next/Confirm button
                            if self.current_page < self.total_pages - 1:
                                # Go to next page
                                self.current_page += 1
                                self._create_components()
                                # Keep selection on next button
                                self.selected_button = 0
                                self.components[self.selected_button].is_selected = True
                                self._render()
                            else:
                                # Confirm action
                                return "CONFIRM"

            self.renderer.show_image()


@dataclass
class GroupShareListScreen(SeedCashButtonListWithNav):
    fingerprint: str = None

    def __post_init__(self):
        if self.fingerprint:
            self.title = self.fingerprint
        super().__post_init__()

        icon_size = GUIConstants.ICON_FONT_SIZE + 12

        if self.fingerprint:
            fingerprint_image = vh.generate_lifehash(self.fingerprint)
            self.paste_images.append(
                (
                    fingerprint_image.resize((icon_size, icon_size)),
                    (3 * GUIConstants.EDGE_PADDING, GUIConstants.EDGE_PADDING),
                )
            )


@dataclass
class VisualGroupShareScreen(BaseTopNavScreen):
    text: str = "Groups"
    threshold: int = 1
    total_members: int = 1
    passphrase: str = ""

    def __post_init__(self):
        self.show_back_button = True
        self.title = f"{self.text} Scheme"
        super().__post_init__()

        # Circle visualization parameters
        self.radius_int = int(self.canvas_width // 5)
        self.circle_radius = min(80, self.radius_int)
        self.circle_center = (
            self.canvas_width // 4,
            GUIConstants.EDGE_PADDING
            + GUIConstants.TOP_NAV_TITLE_FONT_SIZE
            + 20
            + self.circle_radius,
        )

        # Groups controls (left side)
        groups_x = (
            self.canvas_width
            - GUIConstants.EDGE_PADDING
            - GUIConstants.TOP_NAV_BUTTON_SIZE
        )

        # Threshold controls (right side)
        threshold_x = (
            groups_x - GUIConstants.EDGE_PADDING - GUIConstants.TOP_NAV_BUTTON_SIZE
        )

        self.up_btns_y = GUIConstants.TOP_NAV_HEIGHT
        self.down_btns_y = (
            self.canvas_height
            - GUIConstants.TOP_NAV_HEIGHT
            - GUIConstants.TOP_NAV_BUTTON_SIZE
        )

        # Groups up arrow
        self.total_members_up_button = IconButton(
            icon_name=SeedCashIconsConstants.PAGE_UP,
            screen_x=groups_x,
            screen_y=self.up_btns_y,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            is_text_centered=True,
        )
        self.components.append(self.total_members_up_button)

        # Groups down arrow
        self.total_members_down_button = IconButton(
            icon_name=SeedCashIconsConstants.PAGE_DOWN,
            screen_x=groups_x,
            screen_y=self.down_btns_y,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            is_text_centered=True,
        )
        self.components.append(self.total_members_down_button)

        # Threshold up arrow
        self.threshold_up_button = IconButton(
            icon_name=SeedCashIconsConstants.PAGE_UP,
            screen_x=threshold_x,
            screen_y=self.up_btns_y,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            is_text_centered=True,
        )
        self.components.append(self.threshold_up_button)

        # Threshold down button
        self.threshold_down_button = IconButton(
            icon_name=SeedCashIconsConstants.PAGE_DOWN,
            screen_x=threshold_x,
            screen_y=self.down_btns_y,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            is_text_centered=True,
        )
        self.components.append(self.threshold_down_button)

        self._buttons()

        # Set initial selection
        self.selected_key = 1
        self.selected_button = 5
        self.components[self.selected_key].is_selected = True
        self.components[self.selected_button].is_selected = True

    def _buttons(self):
        # Confirm button
        confirm_btn_width = self.canvas_width // 2 - 4 * GUIConstants.EDGE_PADDING
        if self.passphrase is not None:
            self.confirm_button = Button(
                text=_("Confirm"),
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=self.canvas_height
                - GUIConstants.BUTTON_HEIGHT
                - GUIConstants.EDGE_PADDING,
                width=confirm_btn_width,
                height=GUIConstants.BUTTON_HEIGHT,
            )

            # Add Passphrase button
            self.add_passphrase_button = Button(
                text=_("Add Passphrase") if not self.passphrase else _("Passphrase"),
                screen_x=confirm_btn_width + 2 * GUIConstants.EDGE_PADDING,
                screen_y=self.canvas_height
                - GUIConstants.BUTTON_HEIGHT
                - GUIConstants.EDGE_PADDING,
                width=self.canvas_width
                - confirm_btn_width
                - 3 * GUIConstants.EDGE_PADDING,
                height=GUIConstants.BUTTON_HEIGHT,
            )

            self.components.append(self.confirm_button)
            self.components.append(self.add_passphrase_button)

        else:
            self.confirm_button = Button(
                text=_("Confirm"),
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=self.canvas_height
                - GUIConstants.BUTTON_HEIGHT
                - GUIConstants.EDGE_PADDING,
                width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
                height=GUIConstants.BUTTON_HEIGHT,
            )
            self.components.append(self.confirm_button)

    def _update_labels(self):
        """Update the text labels with current values"""
        label_y = (
            2 * self.radius_int
            + 3 * GUIConstants.COMPONENT_PADDING
            + GUIConstants.BUTTON_HEIGHT
        )
        label_x = 4 * GUIConstants.BUTTON_HEIGHT + 2 * GUIConstants.EDGE_PADDING

        self.total_members_label = TextArea(
            text=f"{self.text}:{self.total_members}",
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=label_y,
            width=label_x,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        self.threshold_label = TextArea(
            text=f"Threshold:{self.threshold}",
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=label_y
            + GUIConstants.BUTTON_HEIGHT
            - 2 * GUIConstants.EDGE_PADDING,
            width=label_x,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        self.total_members_label.render()
        self.threshold_label.render()

    def _draw_circle_segments(self):
        """Draw the circle with segments showing groups and threshold"""
        draw = ImageDraw.Draw(self.renderer.canvas)

        # Ensure threshold doesn't exceed groups
        self.threshold = min(self.threshold, self.total_members)

        # Draw the full circle outline
        draw.ellipse(
            [
                self.circle_center[0] - self.circle_radius,
                self.circle_center[1] - self.circle_radius,
                self.circle_center[0] + self.circle_radius,
                self.circle_center[1] + self.circle_radius,
            ],
            outline=GUIConstants.ACCENT_COLOR,
            width=2,
        )

        # If only 1 group, draw full circle filled or empty based on threshold
        if self.total_members == 1:
            fill_color = "white" if self.threshold >= 1 else "#333333"
            draw.ellipse(
                [
                    self.circle_center[0] - self.circle_radius,
                    self.circle_center[1] - self.circle_radius,
                    self.circle_center[0] + self.circle_radius,
                    self.circle_center[1] + self.circle_radius,
                ],
                fill=fill_color,
                width=2,
            )
            return

        # Calculate segment angles for multiple groups
        angle_per_group = 360 / self.total_members
        filled_color = "white"
        empty_color = "#333333"  # Dark gray for unfilled segments

        # Draw each segment
        for i in range(self.total_members):
            start_angle = i * angle_per_group - 90  # Start from top (-90 degrees)
            end_angle = (i + 1) * angle_per_group - 90

            # Determine if this segment should be filled (part of threshold)
            fill_color = filled_color if i < self.threshold else empty_color

            # Draw pie segment
            draw.pieslice(
                [
                    self.circle_center[0] - self.circle_radius,
                    self.circle_center[1] - self.circle_radius,
                    self.circle_center[0] + self.circle_radius,
                    self.circle_center[1] + self.circle_radius,
                ],
                start=start_angle,
                end=end_angle,
                fill=fill_color,
                outline=GUIConstants.BACKGROUND_COLOR,
                width=1,
            )

        # Draw dividing lines between segments (only if more than 1 group)
        if self.total_members > 1:
            for i in range(self.total_members):
                # Calculate the angle for the dividing line at the start of each segment
                line_angle = math.radians(i * angle_per_group - 90)  # Start from top
                line_end = (
                    self.circle_center[0] + self.circle_radius * math.cos(line_angle),
                    self.circle_center[1] + self.circle_radius * math.sin(line_angle),
                )
                draw.line(
                    [self.circle_center, line_end],
                    fill=GUIConstants.BACKGROUND_COLOR,
                    width=2,
                )

    def _render(self):
        super()._render()
        self._update_labels()
        self._draw_circle_segments()  # Draw our custom visualization
        for component in self.components:
            component.render()
        self.renderer.show_image()

    def _run(self):
        is_groups = True
        while True:
            input = self.hw_inputs.wait_for(HardwareButtonsConstants.ALL_KEYS)

            with self.renderer.lock:
                # Clear current selection
                if input == HardwareButtonsConstants.KEY1:
                    if is_groups and self.total_members < 16:
                        self.total_members += 1
                        if (
                            self.total_members > 1
                            and self.threshold == 1
                            and self.text == "Shares"
                        ):
                            self.threshold = 2
                        # Ensure threshold doesn't exceed groups when groups increase
                        self.threshold = min(self.threshold, self.total_members)
                        self.components[self.selected_key].is_selected = False
                        self.components[self.selected_key].render()
                        self.selected_key = 1  # Reset to first button
                        self.components[self.selected_key].is_selected = True
                        self.components[self.selected_key].render()
                    elif not is_groups and self.threshold < 16:
                        # Only increase threshold if it won't exceed groups
                        if self.threshold < self.total_members:
                            self.threshold += 1
                        self.components[self.selected_key].is_selected = False
                        self.components[self.selected_key].render()
                        self.selected_key = 3  # Reset to fourth button
                        self.components[self.selected_key].is_selected = True
                        self.components[self.selected_key].render()
                elif input == HardwareButtonsConstants.KEY2:
                    self.components[self.selected_key].is_selected = False
                    self.components[self.selected_key].render()
                    if is_groups:
                        is_groups = False
                        self.selected_key = 3  # Reset to fourth button
                    else:
                        is_groups = True
                        self.selected_key = 1  # Reset to first button
                    self.components[self.selected_key].is_selected = True
                    self.components[self.selected_key].render()
                elif input == HardwareButtonsConstants.KEY3:
                    if is_groups:
                        if self.total_members > 1:  # Prevent groups from going below 1
                            self.total_members = max(1, self.total_members - 1)
                            # Ensure threshold doesn't exceed groups when groups decrease
                            self.threshold = min(self.threshold, self.total_members)
                        self.components[self.selected_key].is_selected = False
                        self.components[self.selected_key].render()
                        self.selected_key = 2
                        self.components[self.selected_key].is_selected = True
                    else:
                        if (
                            self.total_members > 1
                            and self.threshold <= 2
                            and self.text == "Shares"
                        ):
                            self.threshold = 2
                        else:
                            self.threshold = max(1, self.threshold - 1)

                        self.components[self.selected_key].is_selected = False
                        self.components[self.selected_key].render()
                        self.selected_key = 4
                        self.components[self.selected_key].is_selected = True

                # Handle confirm button and back button
                if input in [
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT,
                ]:
                    if self.top_nav.is_selected:
                        continue

                    if self.selected_button == 5 and self.passphrase is not None:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button = 6
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()
                    else:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button = 5
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()

                if input == HardwareButtonsConstants.KEY_DOWN:
                    if self.top_nav.is_selected:
                        self.top_nav.is_selected = False
                        self.top_nav.render_buttons()
                        self.selected_button = 5
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()

                if input == HardwareButtonsConstants.KEY_UP:
                    if not self.top_nav.is_selected:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.top_nav.is_selected = True
                        self.top_nav.render_buttons()

                if input in [
                    HardwareButtonsConstants.KEY_PRESS,
                ]:
                    if self.top_nav.is_selected:
                        return RET_CODE__BACK_BUTTON
                    if self.selected_button == 5:
                        return ("CONFIRM", self.threshold, self.total_members)
                    if self.selected_button == 6:
                        return ("PASSPHRASE", self.threshold, self.total_members)

                self._render()  # Render the updated screen


@dataclass
class VisualLoadedSchemeScreen(BaseTopNavScreen):
    scheme: Scheme = None

    def __post_init__(self):
        self.show_back_button = True
        super().__post_init__()

        self.group_indices = self.scheme.get_group_indices()

        (
            self.processed_groups,
            self.group_threshold,
            self.total_groups,
            self.completed_groups,
        ) = self.scheme.get_scheme_info()

        self.group_index = 0

        # navigate groups
        self._navigate_groups()

        # Group Circle
        self.group_radius_int = int(self.canvas_width // 6)
        self.group_circle_radius = min(80, self.group_radius_int)
        self.group_circle_center = (
            self.canvas_width // 6 + GUIConstants.EDGE_PADDING,
            GUIConstants.EDGE_PADDING
            + GUIConstants.TOP_NAV_TITLE_FONT_SIZE
            + 20
            + self.group_circle_radius,
        )

        # Share Circle
        self.share_radius_int = int(self.canvas_width // 6)
        self.share_circle_radius = min(80, self.share_radius_int)
        self.share_circle_center = (
            self.canvas_width // 2 + 2 * GUIConstants.EDGE_PADDING,
            GUIConstants.EDGE_PADDING
            + GUIConstants.TOP_NAV_TITLE_FONT_SIZE
            + 20
            + self.share_circle_radius,
        )

        # Groups controls (left side)
        groups_x = (
            self.canvas_width
            - GUIConstants.EDGE_PADDING
            - GUIConstants.TOP_NAV_BUTTON_SIZE
        )

        self.up_btns_y = GUIConstants.TOP_NAV_HEIGHT
        self.down_btns_y = (
            self.canvas_height
            - GUIConstants.TOP_NAV_HEIGHT
            - GUIConstants.TOP_NAV_BUTTON_SIZE
        )

        edit_review_width = 108

        # Edit & Review button
        self.edit_review_button = Button(
            text=_("Edit & Review"),
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.canvas_height
            - GUIConstants.BUTTON_HEIGHT
            - GUIConstants.EDGE_PADDING,
            width=edit_review_width,
            font_size=GUIConstants.BUTTON_FONT_SIZE - 4,
            height=GUIConstants.BUTTON_HEIGHT,
        )
        self.components.append(self.edit_review_button)

        # Add Share button
        self.add_share_button = Button(
            text=_(" Add Share"),
            screen_x=edit_review_width + 2 * GUIConstants.EDGE_PADDING,
            screen_y=self.canvas_height
            - GUIConstants.BUTTON_HEIGHT
            - GUIConstants.EDGE_PADDING,
            font_size=GUIConstants.BUTTON_FONT_SIZE - 4,
            width=edit_review_width,
            height=GUIConstants.BUTTON_HEIGHT,
        )

        self.components.append(self.add_share_button)

        # Groups up arrow
        self.up_button = IconButton(
            icon_name=SeedCashIconsConstants.PAGE_UP,
            screen_x=groups_x,
            screen_y=self.up_btns_y,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            is_text_centered=True,
        )

        # Groups down arrow
        self.down_button = IconButton(
            icon_name=SeedCashIconsConstants.PAGE_DOWN,
            screen_x=groups_x,
            screen_y=self.down_btns_y,
            font_size=GUIConstants.BODY_FONT_SIZE - 3,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            is_text_centered=True,
        )

        self._show_navigate_btns()

        # Set initial selection
        self.selected_button = 1
        self.selected_key = 1

        self.components[self.selected_key].is_selected = True
        self.components[self.selected_button].is_selected = True

    def _show_navigate_btns(self):
        if self.processed_groups > 1:
            self.components.append(self.up_button)
            self.components.append(self.down_button)
            self.selected_key = 3

    def _navigate_groups(self):
        self.shares_count, self.member_threshold = self.scheme.get_group_info(
            self.group_indices[self.group_index]
        )

        self.top_nav.text = f"Group:{self.group_indices[self.group_index]}"
        self.top_nav.render()

    def _update_labels(self):
        """Update the text labels with current values"""
        label_y = (
            max(self.group_circle_center[1], self.share_circle_center[1])
            + self.group_circle_radius
            + GUIConstants.COMPONENT_PADDING
        )

        # Group label (left side)
        self.groups_text = TextArea(
            text=f"Grups:{self.total_groups}",
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=label_y,
            width=self.canvas_width // 2 - GUIConstants.EDGE_PADDING,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        self.groups_progress_text = TextArea(
            text=f"Progr:{self.processed_groups}",
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=label_y
            + GUIConstants.BUTTON_HEIGHT
            - 2 * GUIConstants.EDGE_PADDING,
            width=self.canvas_width // 2 - GUIConstants.EDGE_PADDING,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        self.group_threshold_text = TextArea(
            text=f"Thres:{self.group_threshold}",
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=label_y
            + 2 * GUIConstants.BUTTON_HEIGHT
            - 4 * GUIConstants.EDGE_PADDING,
            width=self.canvas_width // 2 - GUIConstants.EDGE_PADDING,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        # Share label (right side)

        self.current_group_text = TextArea(
            text=f"Group:{self.group_indices[self.group_index]}",
            screen_x=self.canvas_width // 2 - 3 * GUIConstants.EDGE_PADDING,
            screen_y=label_y,
            width=self.canvas_width // 2 + 3 * GUIConstants.EDGE_PADDING,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        self.members_progress_text = TextArea(
            text=f"Progr:{self.shares_count}",
            screen_x=self.canvas_width // 2 - 3 * GUIConstants.EDGE_PADDING,
            screen_y=label_y + GUIConstants.BUTTON_HEIGHT // 2,
            width=self.canvas_width // 2 + 3 * GUIConstants.EDGE_PADDING,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        # Share label (right side)
        self.members_threshold_text = TextArea(
            text=f"Thres:{self.member_threshold}",
            screen_x=self.canvas_width // 2 - 3 * GUIConstants.EDGE_PADDING,
            screen_y=label_y + GUIConstants.BUTTON_HEIGHT,
            width=self.canvas_width // 2 + 3 * GUIConstants.EDGE_PADDING,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        self.groups_text.render()
        self.groups_progress_text.render()
        self.group_threshold_text.render()
        self.current_group_text.render()
        self.members_threshold_text.render()
        self.members_progress_text.render()

    def _draw_circle_segments(self):
        """Draw both circles with segments showing groups and threshold"""
        draw = ImageDraw.Draw(self.renderer.canvas)

        # Draw Group Circle (left)
        self._draw_single_circle(
            draw,
            self.group_circle_center,
            self.group_circle_radius,
            self.total_groups,
            self.group_threshold,
            self.completed_groups,
        )

        # Draw Share Circle (right)
        self._draw_single_circle(
            draw,
            self.share_circle_center,
            self.share_circle_radius,
            self.member_threshold,
            self.member_threshold,
            self.shares_count,
        )

    def _draw_single_circle(
        self, draw, center, radius, total_segments, filled_threshold, filled_progress
    ):
        """Helper method to draw a single circle with segments"""
        # Draw the full circle outline
        draw.ellipse(
            [
                center[0] - radius,
                center[1] - radius,
                center[0] + radius,
                center[1] + radius,
            ],
            outline=GUIConstants.ACCENT_COLOR,
            width=2,
        )

        # If only 1 segment, draw full circle filled or empty
        if total_segments == 1:
            if filled_threshold == 1:
                if filled_progress == 1:
                    fill_color = GUIConstants.ACCENT_COLOR
                else:
                    fill_color = "white"
            else:
                fill_color = "#333333"

            draw.ellipse(
                [
                    center[0] - radius,
                    center[1] - radius,
                    center[0] + radius,
                    center[1] + radius,
                ],
                fill=fill_color,
                width=2,
            )
            return

        # Calculate segment angles for multiple segments
        angle_per_segment = 360 / total_segments
        filled_threshold_color = "white"
        filled_progress_color = GUIConstants.ACCENT_COLOR
        empty_color = "#333333"  # Dark gray for unfilled segments

        # Draw each segment
        for i in range(total_segments):
            start_angle = i * angle_per_segment - 90  # Start from top (-90 degrees)
            end_angle = (i + 1) * angle_per_segment - 90

            # Determine if this segment should be filled (part of threshold)
            if i < filled_threshold:
                if i < filled_progress:
                    # Use filled_progress_color for segments that are filled and reached the threshold
                    fill_color = filled_progress_color
                else:
                    fill_color = filled_threshold_color
            else:
                if i < filled_progress:
                    # Use filled_progress_color for segments that are filled but not reached the threshold
                    fill_color = filled_progress_color
                else:
                    # Use empty_color for segments that are not filled
                    fill_color = empty_color

            # Draw pie segment
            draw.pieslice(
                [
                    center[0] - radius,
                    center[1] - radius,
                    center[0] + radius,
                    center[1] + radius,
                ],
                start=start_angle,
                end=end_angle,
                fill=fill_color,
                outline=GUIConstants.BACKGROUND_COLOR,
                width=1,
            )

        # Draw dividing lines between segments (only if more than 1 segment)
        if total_segments > 1:
            for i in range(total_segments):
                # Calculate the angle for the dividing line
                line_angle = math.radians(i * angle_per_segment - 90)
                line_end = (
                    center[0] + radius * math.cos(line_angle),
                    center[1] + radius * math.sin(line_angle),
                )
                draw.line(
                    [center, line_end],
                    fill=GUIConstants.BACKGROUND_COLOR,
                    width=2,
                )

    def _render(self):
        super()._render()
        self._update_labels()
        self._draw_circle_segments()  # Draw our custom visualization
        for component in self.components:
            component.render()
        self.renderer.show_image()

    def _run(self):
        while True:
            input = self.hw_inputs.wait_for(HardwareButtonsConstants.ALL_KEYS)

            with self.renderer.lock:
                # Clear current selection
                if input == HardwareButtonsConstants.KEY1:
                    if self.processed_groups <= 1:
                        continue

                    self.components[self.selected_key].is_selected = False
                    self.components[self.selected_key].render()
                    self.selected_key = 3
                    self.components[self.selected_key].is_selected = True
                    self.components[self.selected_key].render()

                    if self.group_index < self.processed_groups - 1:
                        self.group_index += 1
                        self._navigate_groups()

                elif input == HardwareButtonsConstants.KEY3:
                    if self.processed_groups <= 1:
                        continue

                    self.components[self.selected_key].is_selected = False
                    self.components[self.selected_key].render()
                    self.selected_key = 4
                    self.components[self.selected_key].is_selected = True
                    self.components[self.selected_key].render()

                    if self.group_index > 0:
                        self.group_index -= 1
                        self._navigate_groups()

                # Handle confirm button and back button
                if input in [
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT,
                ]:
                    if self.top_nav.is_selected:
                        continue

                    if self.selected_button == 1:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button = 2
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()
                    else:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button = 1
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()

                if input == HardwareButtonsConstants.KEY_DOWN:
                    if self.top_nav.is_selected:
                        self.top_nav.is_selected = False
                        self.top_nav.render_buttons()
                        self.selected_button = 1
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()

                if input == HardwareButtonsConstants.KEY_UP:
                    if not self.top_nav.is_selected:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.top_nav.is_selected = True
                        self.top_nav.render_buttons()

                if input in [
                    HardwareButtonsConstants.KEY_PRESS,
                    HardwareButtonsConstants.KEY2,
                ]:
                    if self.top_nav.is_selected:
                        return RET_CODE__BACK_BUTTON
                    if self.selected_button == 1:
                        return "EDIT"
                    if self.selected_button == 2:
                        return "ADD"

                self._render()


@dataclass
class SingleLevelVisualLoadedSchemeScreen(BaseTopNavScreen):
    shares_count: int = 1
    member_threshold: int = 1

    def __post_init__(self):
        self.show_back_button = True
        super().__post_init__()

        # Share Circle
        self.share_radius_int = int(self.canvas_width // 5)
        self.share_circle_radius = min(80, self.share_radius_int)
        self.share_circle_center = (
            self.share_circle_radius + 3 * GUIConstants.EDGE_PADDING,
            self.canvas_height // 2 - GUIConstants.COMPONENT_PADDING,
        )

        edit_review_width = 108
        # Edit & Review button
        self.edit_review_button = Button(
            text=_("Edit & Review"),
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.canvas_height
            - GUIConstants.BUTTON_HEIGHT
            - GUIConstants.EDGE_PADDING,
            width=edit_review_width,
            font_size=GUIConstants.BUTTON_FONT_SIZE - 4,
            height=GUIConstants.BUTTON_HEIGHT,
        )
        self.components.append(self.edit_review_button)

        # Add Share button
        self.add_share_button = Button(
            text=_(" Add Share"),
            screen_x=edit_review_width + 2 * GUIConstants.EDGE_PADDING,
            screen_y=self.canvas_height
            - GUIConstants.BUTTON_HEIGHT
            - GUIConstants.EDGE_PADDING,
            font_size=GUIConstants.BUTTON_FONT_SIZE - 4,
            width=edit_review_width,
            height=GUIConstants.BUTTON_HEIGHT,
        )
        self.components.append(self.add_share_button)

        self.selected_button = 1
        self.components[self.selected_button].is_selected = True

    def _update_labels(self):
        """Update the text labels with current values"""
        label_y = (
            self.canvas_height // 2
            - GUIConstants.BUTTON_HEIGHT
            + GUIConstants.COMPONENT_PADDING
        )

        label_x = (
            self.share_circle_center[0]
            + self.share_circle_radius
            + GUIConstants.COMPONENT_PADDING
        )

        # Share label (right side)
        self.members_progress_text = TextArea(
            text=f"Prog:{self.shares_count}",
            screen_x=label_x,
            screen_y=label_y,
            width=self.canvas_width // 2 + 3 * GUIConstants.EDGE_PADDING,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        self.members_threshold_text = TextArea(
            text=f"Thres:{self.member_threshold}",
            screen_x=label_x,
            screen_y=label_y
            + GUIConstants.BUTTON_HEIGHT
            - 2 * GUIConstants.EDGE_PADDING,
            width=self.canvas_width // 2 + 3 * GUIConstants.EDGE_PADDING,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )

        self.members_threshold_text.render()
        self.members_progress_text.render()

    def _draw_circle_segments(self):
        """Draw both circles with segments showing groups and threshold"""
        draw = ImageDraw.Draw(self.renderer.canvas)

        # Draw Share Circle (right)
        self._draw_single_circle(
            draw,
            self.share_circle_center,
            self.share_circle_radius,
            self.member_threshold,
            self.member_threshold,
            self.shares_count,
        )

    def _draw_single_circle(
        self, draw, center, radius, total_segments, filled_threshold, filled_progress
    ):
        """Helper method to draw a single circle with segments"""
        # Draw the full circle outline
        draw.ellipse(
            [
                center[0] - radius,
                center[1] - radius,
                center[0] + radius,
                center[1] + radius,
            ],
            outline=GUIConstants.ACCENT_COLOR,
            width=2,
        )

        # If only 1 segment, draw full circle filled or empty
        if total_segments == 1:
            if filled_threshold == 1:
                if filled_progress == 1:
                    fill_color = GUIConstants.ACCENT_COLOR
                else:
                    fill_color = "white"
            else:
                fill_color = "#333333"

            draw.ellipse(
                [
                    center[0] - radius,
                    center[1] - radius,
                    center[0] + radius,
                    center[1] + radius,
                ],
                fill=fill_color,
                width=2,
            )
            return

        # Calculate segment angles for multiple segments
        angle_per_segment = 360 / total_segments
        filled_threshold_color = "white"
        filled_progress_color = GUIConstants.ACCENT_COLOR
        empty_color = "#333333"  # Dark gray for unfilled segments

        # Draw each segment
        for i in range(total_segments):
            start_angle = i * angle_per_segment - 90  # Start from top (-90 degrees)
            end_angle = (i + 1) * angle_per_segment - 90

            # Determine if this segment should be filled (part of threshold)
            if i < filled_threshold:
                if i < filled_progress:
                    # Use filled_progress_color for segments that are filled and reached the threshold
                    fill_color = filled_progress_color
                else:
                    fill_color = filled_threshold_color
            else:
                if i < filled_progress:
                    # Use filled_progress_color for segments that are filled but not reached the threshold
                    fill_color = filled_progress_color
                else:
                    # Use empty_color for segments that are not filled
                    fill_color = empty_color

            # Draw pie segment
            draw.pieslice(
                [
                    center[0] - radius,
                    center[1] - radius,
                    center[0] + radius,
                    center[1] + radius,
                ],
                start=start_angle,
                end=end_angle,
                fill=fill_color,
                outline=GUIConstants.BACKGROUND_COLOR,
                width=1,
            )

        # Draw dividing lines between segments (only if more than 1 segment)
        if total_segments > 1:
            for i in range(total_segments):
                # Calculate the angle for the dividing line
                line_angle = math.radians(i * angle_per_segment - 90)
                line_end = (
                    center[0] + radius * math.cos(line_angle),
                    center[1] + radius * math.sin(line_angle),
                )
                draw.line(
                    [center, line_end],
                    fill=GUIConstants.BACKGROUND_COLOR,
                    width=2,
                )

    def _render(self):
        super()._render()
        self._update_labels()
        self._draw_circle_segments()
        for component in self.components:
            component.render()
        self.renderer.show_image()

    def _run(self):
        while True:
            input = self.hw_inputs.wait_for(HardwareButtonsConstants.ALL_KEYS)

            with self.renderer.lock:
                # Handle confirm button and back button
                if input in [
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT,
                ]:
                    if self.top_nav.is_selected:
                        continue

                    if self.selected_button == 1:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button = 2
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()
                    else:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.selected_button = 1
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()

                if input == HardwareButtonsConstants.KEY_DOWN:
                    if self.top_nav.is_selected:
                        self.top_nav.is_selected = False
                        self.top_nav.render_buttons()
                        self.selected_button = 1
                        self.components[self.selected_button].is_selected = True
                        self.components[self.selected_button].render()

                if input == HardwareButtonsConstants.KEY_UP:
                    if not self.top_nav.is_selected:
                        self.components[self.selected_button].is_selected = False
                        self.components[self.selected_button].render()
                        self.top_nav.is_selected = True
                        self.top_nav.render_buttons()

                if input in [
                    HardwareButtonsConstants.KEY_PRESS,
                    HardwareButtonsConstants.KEY2,
                ]:
                    if self.top_nav.is_selected:
                        return RET_CODE__BACK_BUTTON
                    if self.selected_button == 1:
                        return "EDIT"
                    if self.selected_button == 2:
                        return "ADD"

                self._render()
