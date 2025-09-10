import logging

from dataclasses import dataclass
from gettext import gettext as _


from seedcash.hardware.buttons import HardwareButtonsConstants
from seedcash.gui.components import (
    IconTextLine,
    TextArea,
    GUIConstants,
    Button,
)
from seedcash.models import visual_hash as vh

from .screen import (
    RET_CODE__BACK_BUTTON,
    BaseTopNavScreen,
    ButtonListScreen,
    KeyboardScreen,
)

logger = logging.getLogger(__name__)


"""*****************************
Seed Cash Screens
*****************************"""


@dataclass
class SeedCashGenerateSeedScreen(ButtonListScreen, BaseTopNavScreen):
    def __post_init__(self):
        self.is_button_text_centered = False
        self.is_top_nav = True
        self.show_back_button = True
        super().__post_init__()

    def _run(self):
        while True:
            ret = self._run_callback()
            if ret is not None:
                logging.info("Exiting ButtonListScreen due to _run_callback")
                return ret

            user_input = self.hw_inputs.wait_for(
                [
                    HardwareButtonsConstants.KEY_UP,
                    HardwareButtonsConstants.KEY_DOWN,
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT,
                ]
                + HardwareButtonsConstants.KEYS__ANYCLICK
            )

            with self.renderer.lock:
                if not self.top_nav.is_selected and (
                    user_input == HardwareButtonsConstants.KEY_LEFT
                    or (
                        user_input == HardwareButtonsConstants.KEY_UP
                        and self.selected_button == 0
                    )
                ):
                    # SHORTCUT to escape long menu screens!
                    # OR keyed UP from the top of the list.
                    # Move selection up to top_nav
                    # Only move navigation up there if there's something to select
                    if self.top_nav.show_back_button or self.top_nav.show_power_button:
                        self.buttons[self.selected_button].is_selected = False
                        self.buttons[self.selected_button].render()

                        self.top_nav.is_selected = True
                        self.top_nav.render_buttons()

                elif user_input == HardwareButtonsConstants.KEY_UP:
                    if self.top_nav.is_selected:
                        # Can't go up any further
                        pass
                    else:
                        cur_selected_button: Button = self.buttons[self.selected_button]
                        self.selected_button -= 1
                        next_selected_button: Button = self.buttons[
                            self.selected_button
                        ]
                        cur_selected_button.is_selected = False
                        next_selected_button.is_selected = True
                        if (
                            self.has_scroll_arrows
                            and next_selected_button.screen_y
                            - next_selected_button.scroll_y
                            + next_selected_button.height
                            < self.top_nav.height
                        ):
                            # Selected a Button that's off the top of the screen
                            frame_scroll = (
                                cur_selected_button.screen_y
                                - next_selected_button.screen_y
                            )
                            for button in self.buttons:
                                button.scroll_y -= frame_scroll
                            self._render_visible_buttons()
                        else:
                            cur_selected_button.render()
                            next_selected_button.render()

                elif user_input == HardwareButtonsConstants.KEY_DOWN or (
                    self.top_nav.is_selected
                    and user_input == HardwareButtonsConstants.KEY_RIGHT
                ):
                    if self.selected_button == len(self.buttons) - 1:
                        # Already at the bottom of the list. Nowhere to go. But may need
                        # to re-render if we're returning from top_nav; otherwise skip
                        # this update loop.
                        if not self.top_nav.is_selected:
                            continue

                    if self.top_nav.is_selected:
                        self.top_nav.is_selected = False
                        self.top_nav.render_buttons()

                        cur_selected_button = None
                        next_selected_button = self.buttons[self.selected_button]
                        next_selected_button.is_selected = True

                    else:
                        cur_selected_button: Button = self.buttons[self.selected_button]
                        self.selected_button += 1
                        next_selected_button: Button = self.buttons[
                            self.selected_button
                        ]
                        cur_selected_button.is_selected = False
                        next_selected_button.is_selected = True

                    if self.has_scroll_arrows and (
                        next_selected_button.screen_y
                        - next_selected_button.scroll_y
                        + next_selected_button.height
                        > self.down_arrow_img_y
                    ):
                        # Selected a Button that's off the bottom of the screen
                        frame_scroll = (
                            next_selected_button.screen_y - cur_selected_button.screen_y
                        )
                        for button in self.buttons:
                            button.scroll_y += frame_scroll
                        self._render_visible_buttons()
                    else:
                        if cur_selected_button:
                            cur_selected_button.render()
                        next_selected_button.render()

                elif user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                    if self.top_nav.is_selected:
                        return self.top_nav.selected_button
                    return self.selected_button

                # Write the screen updates
                self.renderer.show_image()


@dataclass
class ToolsCoinFlipEntryScreen(KeyboardScreen):

    def __post_init__(self):
        # Override values set by the parent class
        # TRANSLATOR_NOTE: current coin-flip number vs total flips (e.g. flip 3 of 4)
        self.show_back_button = False
        # Specify the keys in the keyboard
        self.rows = 1
        self.cols = 4
        self.key_height = (
            GUIConstants.TOP_NAV_TITLE_FONT_SIZE + 2 + 2 * GUIConstants.EDGE_PADDING
        )
        self.keys_charset = "10"
        self.keyboard_start_y = 2
        # Now initialize the parent class
        super().__post_init__()

        self.components.append(
            TextArea(
                # TRANSLATOR_NOTE: How we call the "front" side result during a coin toss.
                text=f"Introduce the last {self.return_after_n_chars} bits of entropy.",
                screen_y=GUIConstants.COMPONENT_PADDING,
            )
        )


@dataclass
class ToolsCalcFinalWordScreen(ButtonListScreen):
    num_checksum_bits: int = None
    selected_final_bits: str = None
    checksum_bits: str = None
    actual_final_word: str = None

    def __post_init__(self):
        self.is_bottom_list = True
        super().__post_init__()

        text_x = GUIConstants.EDGE_PADDING // 2
        text_y = GUIConstants.TOP_NAV_HEIGHT

        your_input = TextArea(
            text="Your input: {} {}".format(
                self.selected_final_bits, "- " * self.num_checksum_bits
            ),
            screen_x=text_x,
            screen_y=text_y,
        )

        checksum = TextArea(
            text="Checksum: {} {}".format(
                "- " * (11 - self.num_checksum_bits), self.checksum_bits
            ),
            screen_x=text_x,
            screen_y=text_y
            + GUIConstants.BUTTON_FONT_SIZE
            + 2 * GUIConstants.COMPONENT_PADDING,
        )

        final_word = TextArea(
            text=f"Final word:",
            screen_x=text_x,
            screen_y=text_y
            + 2 * GUIConstants.BUTTON_FONT_SIZE
            + 4 * GUIConstants.COMPONENT_PADDING,
            is_text_centered=True,
        )

        actual_final_word = Button(
            text=f"{self.actual_final_word}",
            screen_x=2 * GUIConstants.EDGE_PADDING,
            screen_y=text_y
            + 3 * GUIConstants.BUTTON_FONT_SIZE
            + 5 * GUIConstants.COMPONENT_PADDING,
            font_size=GUIConstants.BODY_FONT_SIZE + 8,
            width=self.canvas_width - 4 * GUIConstants.EDGE_PADDING,
            background_color=GUIConstants.INACTIVE_COLOR,
        )

        self.components.append(your_input)
        self.components.append(checksum)
        self.components.append(final_word)
        self.components.append(actual_final_word)


@dataclass
class ToolsCalcFinalWordDoneScreen(ButtonListScreen):
    final_word: str = None
    fingerprint: str = None

    def __post_init__(self):
        # Manually specify 12 vs 24 case for easier ordinal translation
        self.is_bottom_list = True

        super().__post_init__()

        self.components.append(
            TextArea(
                text=f"""\"{self.final_word}\"""",
                font_size=26,
                is_text_centered=True,
                screen_y=2 * GUIConstants.COMPONENT_PADDING,
            )
        )

        # Generate fingerprint image using visual hash
        fingerprint_image = vh.generate_lifehash(self.fingerprint)

        # Calculate the icon size to match the original icon size
        icon_size = GUIConstants.ICON_FONT_SIZE + 12

        # Calculate position for the fingerprint display
        fingerprint_y = (
            self.components[-1].screen_y
            + self.components[-1].height
            + 3 * GUIConstants.COMPONENT_PADDING
        )

        self.components.append(
            IconTextLine(
                icon_name=None,  # No icon since we're using the actual image
                # TRANSLATOR_NOTE: a label for the shortened Key-id of a BIP-32 master HD wallet
                label_text=_("fingerprint"),
                value_text=self.fingerprint,
                is_text_centered=True,
                screen_y=fingerprint_y,
            )
        )

        # Calculate position for the fingerprint image (to the left of the text)
        image_x = (self.canvas_width - icon_size) // 2 - 60  # Offset to left of text
        image_y = fingerprint_y - (icon_size // 4)  # Align with text baseline

        # Add the fingerprint image to paste_images
        self.paste_images.append(
            (fingerprint_image.resize((icon_size, icon_size)), (image_x, image_y))
        )
