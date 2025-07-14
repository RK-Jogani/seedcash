import logging

from dataclasses import dataclass
from gettext import gettext as _


from seedcash.hardware.buttons import HardwareButtonsConstants
from seedcash.gui.components import (
    Fonts,
    IconButton,
    IconTextLine,
    SeedSignerIconConstants,
    TextArea,
    SeedCashGuiConstants,
    GUIConstants,
)

from .screen import (
    RET_CODE__BACK_BUTTON,
    BaseScreen,
    ButtonListScreen,
    KeyboardScreen,
)

logger = logging.getLogger(__name__)


"""*****************************
Seed Cash Screens
*****************************"""


# SeedCashLoadSeedScreen is used to load a seed in the Seed Cash flow.
# Reminder Screen
@dataclass
class SeedCashGenerateSeedScreen(BaseScreen):
    step1: str = _("Step 1: Read carefully seedcash.com/explication")
    stpe2: str = _("Step 2: Considering the explanation, generate your entropy")
    step3: str = _("Step 3: Do the checksum")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.selected_button = 0  # 0: NEXT, 1: BACK

        # Configure button layout
        self.button_height = SeedCashGuiConstants.NAVIGATION_BUTTON_SIZE
        min_button_width = 100
        available_width = self.canvas_width - 3 * SeedCashGuiConstants.PADDING
        self.button_width = max(min_button_width, available_width // 3)
        self.button_y = (
            self.canvas_height - self.button_height - SeedCashGuiConstants.PADDING
        )

        # Position buttons with a visual separator
        self.next_button_x = (
            self.canvas_width - SeedCashGuiConstants.PADDING - self.button_width
        )
        self.back_button_x = SeedCashGuiConstants.PADDING

        # Calculate step text positions
        self.step1_y = 4 * SeedCashGuiConstants.PADDING
        self.step2_y = (
            self.step1_y
            + SeedCashGuiConstants.PADDING
            + 2 * SeedCashGuiConstants.TEXT_FONT_SIZE
        )
        self.step3_y = (
            self.step2_y
            + SeedCashGuiConstants.PADDING
            + 2 * SeedCashGuiConstants.TEXT_FONT_SIZE
        )

        # Initialize text area
        self.text_x = SeedCashGuiConstants.PADDING

        self.step1_text = TextArea(
            text=self.step1,
            screen_x=self.text_x,
            screen_y=self.step1_y,
            width=self.canvas_width - 2 * SeedCashGuiConstants.PADDING,
            font_size=SeedCashGuiConstants.TEXT_FONT_SIZE,
            is_text_centered=True,
        )

        self.step2_text = TextArea(
            text=self.stpe2,
            screen_x=self.text_x,
            screen_y=self.step2_y,
            width=self.canvas_width - 2 * SeedCashGuiConstants.PADDING,
            font_size=SeedCashGuiConstants.TEXT_FONT_SIZE,
            is_text_centered=True,
        )

        self.step3_text = TextArea(
            text=self.step3,
            screen_x=self.text_x,
            screen_y=self.step3_y,
            width=self.canvas_width - 2 * SeedCashGuiConstants.PADDING,
            font_size=SeedCashGuiConstants.TEXT_FONT_SIZE,
            is_text_centered=True,
        )

        self.components.append(self.step1_text)
        self.components.append(self.step2_text)
        self.components.append(self.step3_text)

    def draw_buttons(self):
        # Draw visual separator between buttons
        separator_x = self.canvas_width // 2
        self.image_draw.line(
            [
                (separator_x, self.button_y),
                (separator_x, self.button_y + self.button_height),
            ],
            fill=SeedCashGuiConstants.BACKGROUND_COLOR,
            width=2,
        )

        # Draw BACK button
        is_back_selected = self.selected_button == 1
        back_btn = IconButton(
            icon_name=SeedSignerIconConstants.BACK,
            icon_size=SeedCashGuiConstants.ICON_INLINE_FONT_SIZE,
            screen_x=self.back_button_x,
            screen_y=self.button_y,
            width=SeedCashGuiConstants.NAVIGATION_BUTTON_SIZE,
            height=SeedCashGuiConstants.NAVIGATION_BUTTON_SIZE,
            selected_color=(
                SeedCashGuiConstants.ACCENT_COLOR if is_back_selected else None
            ),
            is_selected=is_back_selected,
        )

        back_btn.render()

        # Draw NEXT button with emphasis
        is_next_selected = self.selected_button == 0
        next_btn = IconButton(
            icon_name=SeedSignerIconConstants.CHEVRON_RIGHT,
            icon_size=SeedCashGuiConstants.ICON_INLINE_FONT_SIZE,
            screen_x=self.canvas_width
            - SeedCashGuiConstants.NAVIGATION_BUTTON_SIZE
            - SeedCashGuiConstants.PADDING,
            screen_y=self.button_y,
            width=SeedCashGuiConstants.NAVIGATION_BUTTON_SIZE,
            height=SeedCashGuiConstants.NAVIGATION_BUTTON_SIZE,
            selected_color=(
                SeedCashGuiConstants.ACCENT_COLOR if is_next_selected else None
            ),
            is_selected=is_next_selected,
        )
        next_btn.render()

    def _run(self):
        from time import time

        last_interaction = time()
        INACTIVITY_TIMEOUT = 300  # 5 minutes

        while True:
            current_time = time()
            if current_time - last_interaction > INACTIVITY_TIMEOUT:
                return -1  # Timeout

            self.draw_buttons()
            self.renderer.show_image()

            user_input = self.hw_inputs.wait_for(
                [HardwareButtonsConstants.KEY_LEFT, HardwareButtonsConstants.KEY_RIGHT]
                + HardwareButtonsConstants.KEYS__ANYCLICK,
            )

            if not user_input:
                continue

            last_interaction = time()

            if user_input == HardwareButtonsConstants.KEY_LEFT:
                self.selected_button = 1
            elif user_input == HardwareButtonsConstants.KEY_RIGHT:
                self.selected_button = 0
            elif user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                return self.selected_button


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
                text="Introduce the last 7 bits of entropy",
                screen_y=GUIConstants.COMPONENT_PADDING,
            )
        )


@dataclass
class ToolsCalcFinalWordScreen(ButtonListScreen):
    selected_final_word: str = None
    selected_final_bits: str = None
    checksum_bits: str = None
    actual_final_word: str = None

    def __post_init__(self):
        self.is_bottom_list = True
        super().__post_init__()

        # First what's the total bit display width and where do the checksum bits start?
        bit_font_size = (
            GUIConstants.BUTTON_FONT_SIZE + 2
        )  # bit font size should not vary by locale
        font = Fonts.get_font(
            GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME, bit_font_size
        )
        (left, top, bit_display_width, bit_font_height) = font.getbbox(
            "0" * 11, anchor="lt"
        )
        (left, top, checksum_x, bottom) = font.getbbox(
            "0" * (11 - len(self.checksum_bits)), anchor="lt"
        )
        bit_display_x = int((self.canvas_width - bit_display_width) / 2)
        checksum_x += bit_display_x

        y_spacer = GUIConstants.COMPONENT_PADDING

        # Display the user's additional entropy input
        if self.selected_final_word:
            selection_text = self.selected_final_word
            keeper_selected_bits = self.selected_final_bits[
                : 11 - len(self.checksum_bits)
            ]

            # The word's least significant bits will be rendered differently to convey
            # the fact that they're being discarded.
            discard_selected_bits = self.selected_final_bits[
                -1 * len(self.checksum_bits) :
            ]
        else:
            # User entered coin flips or all zeros
            selection_text = self.selected_final_bits
            keeper_selected_bits = self.selected_final_bits

            # We'll append spacer chars to preserve the vertical alignment (most
            # significant n bits always rendered in same column)
            discard_selected_bits = "_" * (len(self.checksum_bits))

        # TRANSLATOR_NOTE: The additional entropy the user supplied (e.g. coin flips)
        your_input = _('Your input: "{}"').format(selection_text)
        self.components.append(
            TextArea(
                text=your_input,
                screen_y=GUIConstants.COMPONENT_PADDING
                + GUIConstants.COMPONENT_PADDING
                - 2,  # Nudge to last line doesn't get too close to "Next" button
                height_ignores_below_baseline=True,  # Keep the next line (bits display) snugged up, regardless of text rendering below the baseline
            )
        )

        # ...and that entropy's associated 11 bits
        screen_y = self.components[-1].screen_y + self.components[-1].height + y_spacer
        first_bits_line = TextArea(
            text=keeper_selected_bits,
            font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            font_size=bit_font_size,
            edge_padding=0,
            screen_x=bit_display_x,
            screen_y=screen_y,
            is_text_centered=False,
        )
        self.components.append(first_bits_line)

        # Render the least significant bits that will be replaced by the checksum in a
        # de-emphasized font color.
        if "_" in discard_selected_bits:
            screen_y += int(
                first_bits_line.height / 2
            )  # center the underscores vertically like hypens
        self.components.append(
            TextArea(
                text=discard_selected_bits,
                font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
                font_color=GUIConstants.LABEL_FONT_COLOR,
                font_size=bit_font_size,
                edge_padding=0,
                screen_x=checksum_x,
                screen_y=screen_y,
                is_text_centered=False,
            )
        )

        # Show the checksum...
        self.components.append(
            TextArea(
                # TRANSLATOR_NOTE: A function of "x" to be used for detecting errors in "x"
                text=_("Checksum"),
                edge_padding=0,
                screen_y=first_bits_line.screen_y
                + first_bits_line.height
                + 2 * GUIConstants.COMPONENT_PADDING,
                height_ignores_below_baseline=True,  # Keep the next line (bits display) snugged up, regardless of text rendering below the baseline
            )
        )

        # ...and its actual bits. Prepend spacers to keep vertical alignment
        checksum_spacer = "_" * (11 - len(self.checksum_bits))

        screen_y = self.components[-1].screen_y + self.components[-1].height + y_spacer

        # This time we de-emphasize the prepended spacers that are irrelevant
        self.components.append(
            TextArea(
                text=checksum_spacer,
                font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
                font_color=GUIConstants.LABEL_FONT_COLOR,
                font_size=bit_font_size,
                edge_padding=0,
                screen_x=bit_display_x,
                screen_y=screen_y
                + int(
                    first_bits_line.height / 2
                ),  # center the underscores vertically like hypens
                is_text_centered=False,
            )
        )

        # And especially highlight (orange!) the actual checksum bits
        self.components.append(
            TextArea(
                text=self.checksum_bits,
                font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
                font_size=bit_font_size,
                font_color=GUIConstants.ACCENT_COLOR,
                edge_padding=0,
                screen_x=checksum_x,
                screen_y=screen_y,
                is_text_centered=False,
            )
        )

        # And now the *actual* final word after merging the bit data
        self.components.append(
            TextArea(
                # TRANSLATOR_NOTE: labeled presentation of the last word in a BIP-39 mnemonic seed phrase.
                text=_('Final Word: "{}"').format(self.actual_final_word),
                screen_y=self.components[-1].screen_y
                + self.components[-1].height
                + 2 * GUIConstants.COMPONENT_PADDING,
                height_ignores_below_baseline=True,  # Keep the next line (bits display) snugged up, regardless of text rendering below the baseline
            )
        )

        # Once again show the bits that came from the user's entropy...
        num_checksum_bits = len(self.checksum_bits)
        user_component = self.selected_final_bits[: 11 - num_checksum_bits]
        screen_y = self.components[-1].screen_y + self.components[-1].height + y_spacer
        self.components.append(
            TextArea(
                text=user_component,
                font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
                font_size=bit_font_size,
                edge_padding=0,
                screen_x=bit_display_x,
                screen_y=screen_y,
                is_text_centered=False,
            )
        )

        # ...and append the checksum's bits, still highlighted in orange
        self.components.append(
            TextArea(
                text=self.checksum_bits,
                font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
                font_color=GUIConstants.ACCENT_COLOR,
                font_size=bit_font_size,
                edge_padding=0,
                screen_x=checksum_x,
                screen_y=screen_y,
                is_text_centered=False,
            )
        )


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

        self.components.append(
            IconTextLine(
                icon_name=SeedSignerIconConstants.FINGERPRINT,
                icon_color=GUIConstants.INFO_COLOR,
                # TRANSLATOR_NOTE: a label for the shortened Key-id of a BIP-32 master HD wallet
                label_text=_("fingerprint"),
                value_text=self.fingerprint,
                is_text_centered=True,
                screen_y=self.components[-1].screen_y
                + self.components[-1].height
                + 3 * GUIConstants.COMPONENT_PADDING,
            )
        )
