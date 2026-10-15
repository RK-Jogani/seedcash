import logging

from dataclasses import dataclass
from gettext import gettext as _


from seedcash.hardware.buttons import HardwareButtonsConstants
from seedcash.gui.components import (
    IconTextLine,
    TextArea,
    RoundedTextArea,
    GUIConstants,
    SeedCashIconsConstants,
    Button,
    IconButton
)
from seedcash.models import visual_hash as vh

from .screen import (
    SeedCashButtonListWithNav,
    ButtonListScreen,
    BaseScreen,
)

logger = logging.getLogger(__name__)


"""*****************************
Seed Cash Screens
*****************************"""


@dataclass
class SeedCashGenerateSeedScreen(SeedCashButtonListWithNav):
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
class ToolsCoinFlipEntryScreen(BaseScreen):
    # max number of bits to enter mnemonic
    max_bits: int = 0

    def __post_init__(self):
        self.bits = ""
        super().__post_init__()
        self._render_buttons()

    def _render_buttons(self):

        component_y = 2 * GUIConstants.EDGE_PADDING
        self.components.append(
            TextArea(
                text=f"Introduce the last {self.max_bits} bits of entropy.",
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=component_y,
            )
        )

        component_y += GUIConstants.TOP_NAV_HEIGHT + 2 * GUIConstants.COMPONENT_PADDING
        button_height = GUIConstants.BUTTON_HEIGHT

        self.components.append(
            RoundedTextArea(
                text=self.bits,
                height=button_height,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=component_y,
            )
        )

        component_y = self.canvas_height - 2 * button_height - 2 * GUIConstants.COMPONENT_PADDING
        width = (self.canvas_width - 4 * GUIConstants.EDGE_PADDING) // 3
        
        self.components.append(
            Button(
                text="0",
                width=width,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=component_y,
            )
        )

        self.components.append(
            Button(
                text="1",
                width=width,
                screen_x=GUIConstants.EDGE_PADDING * 2 + width,
                screen_y=component_y,
            )
        )

        self.components.append(
            IconButton(
                icon_name=SeedCashIconsConstants.DELETE,
                width=width,
                screen_x=GUIConstants.EDGE_PADDING * 3 + 2 * width,
                screen_y=component_y,
            )
        )

        component_y += button_height + GUIConstants.COMPONENT_PADDING
        # This button confirm button must be below the canva
        self.components.append(
            Button(
                text="Confirm",
                width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=component_y,
            )
        )
        self.selected_button = 2
        self.components[self.selected_button].is_selected = True

    def _button_pressed(self, button: str, bits: str) -> str:
        if button == "0" or button == "1":
            if len(bits) < self.max_bits:
                bits += button
        elif button == "BACKSPACE":
            bits = bits[:-1]
        elif button == "CLEAR":
            bits = ""
        return bits

    def _run(self):
        last_button = 2
        while True:
            user_input = self.hw_inputs.wait_for(
                HardwareButtonsConstants.KEYS__LEFT_RIGHT_UP_DOWN
                + HardwareButtonsConstants.KEYS__ANYCLICK
            )

            with self.renderer.lock:
                if user_input == HardwareButtonsConstants.KEY_LEFT:
                    next_button = {3: 2, 4:3}.get(self.selected_button)
                elif user_input == HardwareButtonsConstants.KEY_RIGHT:
                    next_button = {2: 3, 3: 4}.get(self.selected_button)
                elif user_input == HardwareButtonsConstants.KEY_UP:
                    next_button = {5:last_button}.get(self.selected_button)
                elif user_input == HardwareButtonsConstants.KEY_DOWN:
                    last_button = self.selected_button
                    next_button = {2: 5, 3:5, 4:5}.get(self.selected_button)
                else:
                    next_button = None

                if next_button is not None:
                    self.components[self.selected_button].is_selected = False
                    self.components[self.selected_button].render()
                    self.selected_button = next_button
                    self.components[self.selected_button].is_selected = True
                    self.components[self.selected_button].render()

                elif user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                    button = {
                        2: "0",
                        3: "1",
                        4: "BACKSPACE",
                        5: "CONFIRM",
                    }[self.selected_button]
                    if button == "CONFIRM":
                        if len(self.bits) != self.max_bits:
                            continue
                        return self.bits

                    self.bits = self._button_pressed(button, self.bits)
                    self.components[1] = RoundedTextArea(
                        text=self.bits,
                        height=GUIConstants.BUTTON_HEIGHT,
                        screen_x=GUIConstants.EDGE_PADDING,
                        screen_y=(
                            4 * GUIConstants.EDGE_PADDING 
                            + GUIConstants.TOP_NAV_HEIGHT
                        ),
                    )
                    self.components[1].render()

                self.renderer.show_image()



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
            text="Your input: {}".format(self.selected_final_bits),
            screen_x=text_x,
            screen_y=text_y,
        )

        checksum = TextArea(
            text=f"Checksum: {self.checksum_bits}",
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
