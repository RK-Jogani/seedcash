from dataclasses import dataclass

from seedcash.hardware.buttons import HardwareButtonsConstants

from seedcash.gui.components import (
    TextArea,
    RoundedTextArea,
    GUIConstants,
    SeedCashIconsConstants,
    Button,
    IconButton
)

from .screen import (
    ButtonListScreen,
    BaseScreen,
)

# Set up logging for this module
import logging
logger = logging.getLogger(__name__)



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
