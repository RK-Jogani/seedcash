import logging
import math

from dataclasses import dataclass
from gettext import gettext as _
from PIL import Image, ImageDraw, ImageFilter
from typing import List

import qrcode

from seedcash.hardware.buttons import HardwareButtonsConstants
from seedcash.gui.components import (
    Button,
    FontAwesomeIconConstants,
    Fonts,
    IconButton,
    IconTextLine,
    SeedSignerIconConstants,
    TextArea,
    GUIConstants,
)

from seedcash.gui.keyboard import Keyboard, TextEntryDisplay

from .screen import (
    RET_CODE__BACK_BUTTON,
    BaseScreen,
    BaseTopNavScreen,
    ButtonListScreen,
    ButtonOption,
    KeyboardScreen,
    WarningEdgesMixin,
)

logger = logging.getLogger(__name__)


"""*****************************
Seed Cash Screens
*****************************"""


# SeedCashLoadSeedScreen is used to load a seed in the Seed Cash flow.
# Reminder Screen
@dataclass
class SeedCashLoadSeedScreen(BaseScreen):
    head: str = _("Remember!")
    body: str = _("Seedcash only supports 12 seed words")
    text: str = "Enter your mnemonic seed word by word and passphrase."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.button_label = "NEXT"
        self.selected_button = 0  # 0: NEXT, 1: BACK

        # Configure button layout
        self.button_height = GUIConstants.BUTTON_HEIGHT
        min_button_width = 100
        available_width = self.canvas_width - 3 * GUIConstants.EDGE_PADDING
        self.button_width = max(min_button_width, available_width // 3)
        self.button_y = (
            self.canvas_height - self.button_height - GUIConstants.EDGE_PADDING
        )

        # Position buttons with a visual separator
        self.next_button_x = (
            self.canvas_width - GUIConstants.EDGE_PADDING - self.button_width
        )
        self.back_button_x = GUIConstants.EDGE_PADDING

        # Calculate head and body text positions
        self.head_y = 3 * GUIConstants.EDGE_PADDING
        self.body_y = (
            self.head_y
            + GUIConstants.TOP_NAV_TITLE_FONT_SIZE
            + GUIConstants.COMPONENT_PADDING
        )
        self.text_y = (
            self.body_y
            + 3 * GUIConstants.BUTTON_FONT_SIZE
            + GUIConstants.COMPONENT_PADDING
        )

        self.head_text = TextArea(
            text=self.head,
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.head_y,
            is_text_centered=True,
            font_name=GUIConstants.TOP_NAV_TITLE_FONT_NAME,
            font_size=GUIConstants.TOP_NAV_TITLE_FONT_SIZE,
            width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
        )
        self.body_text = TextArea(
            text=self.body,
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.body_y,
            is_text_centered=True,
            font_name=GUIConstants.BODY_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            width=self.canvas_width - GUIConstants.EDGE_PADDING,
        )
        self.text_area = TextArea(
            text=self.text,
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.text_y,
            is_text_centered=True,
            font_name=GUIConstants.BODY_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            width=self.canvas_width - GUIConstants.EDGE_PADDING,
        )

        self.components.append(self.head_text)
        self.components.append(self.body_text)
        self.components.append(self.text_area)
        self.text_area.render()

    def draw_buttons(self):
        # Draw visual separator between buttons
        separator_x = self.canvas_width // 2
        self.image_draw.line(
            [
                (separator_x, self.button_y),
                (separator_x, self.button_y + self.button_height),
            ],
            fill=GUIConstants.BACKGROUND_COLOR,
            width=2,
        )

        # Draw BACK button
        is_back_selected = self.selected_button == 1
        back_btn = IconButton(
            icon_name=SeedSignerIconConstants.BACK,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            screen_x=self.back_button_x,
            screen_y=self.button_y,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            selected_color=GUIConstants.ACCENT_COLOR if is_back_selected else None,
            is_selected=is_back_selected,
        )

        back_btn.render()

        # Draw NEXT button with emphasis
        is_next_selected = self.selected_button == 0
        next_btn = IconButton(
            icon_name=SeedSignerIconConstants.CHEVRON_RIGHT,
            text=self.button_label,
            is_text_centered=True,
            is_icon_inline=True,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            screen_x=self.canvas_width
            - GUIConstants.TOP_NAV_BUTTON_SIZE
            - GUIConstants.EDGE_PADDING,
            screen_y=self.canvas_height
            - GUIConstants.TOP_NAV_BUTTON_SIZE
            - GUIConstants.EDGE_PADDING,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
            selected_color=GUIConstants.ACCENT_COLOR if is_next_selected else None,
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


# display the seed words entered by the user in a grid layout
@dataclass
class SeedCashSeedWordsScreen(BaseScreen):
    """Screen to display the seed words entered by the user in a grid layout.
    This is used to display the seed words entered by the user in the SeedCash flow.
    """

    seed_words: list = None

    def __init__(self, seed_words: list):
        super().__init__()
        self.seed_words = seed_words

        # Display seed words in a grid (4 words per line)
        word_height = GUIConstants.BUTTON_HEIGHT
        word_width = (
            int((self.canvas_width - 3 * GUIConstants.COMPONENT_PADDING) / 3) - 2
        )
        initial_y = 2 * GUIConstants.COMPONENT_PADDING
        initial_x = GUIConstants.EDGE_PADDING

        # example list
        # seed_words=['abandon', 'abandon', 'abandon', 'abandon', 'abandon', 'abandon', 'abandon', 'abandon', 'abandon', 'abandon', 'abandon', 'about']

        self.btn_data = []
        for i, word in enumerate(self.seed_words):
            btn = Button(
                text=f"{i+1}. {word}",
                screen_x=initial_x
                + (i % 3) * (word_width + GUIConstants.COMPONENT_PADDING),
                screen_y=initial_y
                + (i // 3) * (word_height + GUIConstants.COMPONENT_PADDING),
                width=word_width,
                height=word_height,
                font_size=10,
                is_text_centered=True,
                is_scrollable_text=True,
            )
            self.btn_data.append(btn)

    def draw_buttons(self):
        """Draw the seed words as buttons in a grid layout."""
        self.image_draw.rectangle(
            (
                GUIConstants.EDGE_PADDING,
                GUIConstants.EDGE_PADDING,
                self.canvas_width - GUIConstants.EDGE_PADDING,
                self.canvas_height - GUIConstants.EDGE_PADDING,
            ),
            fill=GUIConstants.BACKGROUND_COLOR,
        )

        # Draw each seed word button
        for i, btn in enumerate(self.btn_data):
            btn.render()

        # confirm button
        confirm_button = Button(
            text=_("Confirm"),
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.canvas_height
            - GUIConstants.BUTTON_HEIGHT
            - GUIConstants.EDGE_PADDING,
            width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
            height=GUIConstants.BUTTON_HEIGHT,
            is_text_centered=True,
            is_selected=True,
        )
        confirm_button.render()

    def _run(self):
        """Run the screen and wait for user input to confirm the seed words."""
        while True:

            self.draw_buttons()
            self.renderer.show_image()

            user_input = self.hw_inputs.wait_for(
                HardwareButtonsConstants.KEYS__ANYCLICK
            )

            if user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                return "CONFIRM"  # User confirmed the seed words


"""*****************************
Seed Signer Code Screens
*****************************"""


@dataclass
class SeedMnemonicEntryScreen(BaseTopNavScreen):
    initial_letters: list = None
    wordlist: list = None

    def __post_init__(self):
        super().__post_init__()

        self.possible_alphabet = "abcdefghijklmnopqrstuvwxyz"

        # Measure the width required to display the longest word in the English bip39
        # wordlist.
        # TODO: If we ever support other wordlist languages, adjust accordingly.
        matches_list_highlight_font_name = GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME
        matches_list_highlight_font_size = GUIConstants.BUTTON_FONT_SIZE + 4
        (left, top, right, bottom) = Fonts.get_font(
            matches_list_highlight_font_name, matches_list_highlight_font_size
        ).getbbox("mushroom", anchor="ls")
        matches_list_max_text_width = right - left
        matches_list_button_width = (
            matches_list_max_text_width + 2 * GUIConstants.COMPONENT_PADDING
        )

        # Set up the keyboard params
        self.keyboard_width = (
            self.canvas_width - GUIConstants.EDGE_PADDING - matches_list_button_width
        )
        text_entry_display_y = self.top_nav.height
        text_entry_display_height = 30

        self.arrow_up_is_active = False
        self.arrow_down_is_active = False

        # TODO: support other BIP39 languages/charsets
        self.keyboard = Keyboard(
            draw=self.image_draw,
            charset=self.possible_alphabet,
            rows=5,
            cols=6,
            rect=(
                GUIConstants.EDGE_PADDING,
                text_entry_display_y + text_entry_display_height + 6,
                GUIConstants.EDGE_PADDING + self.keyboard_width,
                self.canvas_height,
            ),
            auto_wrap=[Keyboard.WRAP_LEFT, Keyboard.WRAP_RIGHT],
        )

        self.text_entry_display = TextEntryDisplay(
            canvas=self.canvas,
            rect=(
                GUIConstants.EDGE_PADDING,
                text_entry_display_y,
                GUIConstants.EDGE_PADDING + self.keyboard.width,
                text_entry_display_y + text_entry_display_height,
            ),
            is_centered=False,
            cur_text="".join(self.initial_letters),
        )

        self.letters = self.initial_letters

        # Initialize the current matches
        self.possible_words = []
        if len(self.letters) > 1:
            self.letters.append(" ")  # "Lock in" the last letter as if KEY_PRESS
            self.calc_possible_alphabet()
            self.keyboard.update_active_keys(active_keys=self.possible_alphabet)
            self.keyboard.set_selected_key(selected_letter=self.letters[-2])
        else:
            self.keyboard.set_selected_key(selected_letter=self.letters[-1])

        self.matches_list_x = self.canvas_width - matches_list_button_width
        self.matches_list_y = self.top_nav.height
        self.highlighted_row_y = int(
            (self.canvas_height - GUIConstants.BUTTON_HEIGHT) / 2
        )

        self.matches_list_highlight_button = Button(
            text="abcdefghijklmnopqrstuvwxyz",
            is_text_centered=False,
            font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 4,
            screen_x=self.matches_list_x,
            screen_y=self.highlighted_row_y,
            width=self.canvas_width
            - self.matches_list_x
            + GUIConstants.COMPONENT_PADDING,
            height=int(0.75 * GUIConstants.BUTTON_HEIGHT),
            is_scrollable_text=False,
        )

        arrow_button_width = GUIConstants.BUTTON_HEIGHT + GUIConstants.EDGE_PADDING
        arrow_button_height = int(0.75 * GUIConstants.BUTTON_HEIGHT)
        self.matches_list_up_button = IconButton(
            icon_name=FontAwesomeIconConstants.ANGLE_UP,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE + 2,
            is_text_centered=False,
            screen_x=self.canvas_width
            - arrow_button_width
            + GUIConstants.COMPONENT_PADDING,
            screen_y=self.highlighted_row_y
            - 3 * GUIConstants.COMPONENT_PADDING
            - GUIConstants.BUTTON_HEIGHT,
            width=arrow_button_width,
            height=arrow_button_height,
        )

        self.matches_list_down_button = IconButton(
            icon_name=FontAwesomeIconConstants.ANGLE_DOWN,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE + 2,
            is_text_centered=False,
            screen_x=self.canvas_width
            - arrow_button_width
            + GUIConstants.COMPONENT_PADDING,
            screen_y=self.highlighted_row_y
            + GUIConstants.BUTTON_HEIGHT
            + 3 * GUIConstants.COMPONENT_PADDING,
            width=arrow_button_width,
            height=arrow_button_height,
        )

        self.word_font = Fonts.get_font(
            GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            GUIConstants.BUTTON_FONT_SIZE + 4,
        )
        (left, top, right, bottom) = self.word_font.getbbox(
            "abcdefghijklmnopqrstuvwxyz", anchor="ls"
        )
        self.word_font_height = -1 * top
        self.matches_list_row_height = (
            self.word_font_height + GUIConstants.COMPONENT_PADDING
        )

    def calc_possible_alphabet(self, new_letter=False):
        if (self.letters and len(self.letters) > 1 and new_letter == False) or (
            len(self.letters) > 0 and new_letter == True
        ):
            search_letters = self.letters[:]
            if new_letter == False:
                search_letters.pop()
            self.calc_possible_words()
            letter_num = len(search_letters)
            possible_letters = []
            for word in self.possible_words:
                if len(word) - 1 >= letter_num:
                    possible_letters.append(word[letter_num])
            # remove duplicates and keep order
            self.possible_alphabet = list(dict.fromkeys(possible_letters))[:]
        else:
            self.possible_alphabet = "abcdefghijklmnopqrstuvwxyz"
            self.possible_words = []

    def calc_possible_words(self):
        self.possible_words = [
            i for i in self.wordlist if i.startswith("".join(self.letters).strip())
        ]
        self.selected_possible_words_index = 0

    def render_possible_matches(self, highlight_word=None):
        """Internal helper method to render the KEY 1, 2, 3 word candidates.
        (has access to all vars in the parent's context)
        """
        # Render the possible matches to a temp ImageDraw surface and paste it in
        # BUT render the currently highlighted match as a normal Button element

        if not self.possible_words:
            # Clear the right panel
            self.renderer.draw.rectangle(
                (
                    self.matches_list_x,
                    self.top_nav.height,
                    self.canvas_width,
                    self.matches_list_y,
                ),
                fill=GUIConstants.BACKGROUND_COLOR,
            )
            return

        img = Image.new(
            "RGB",
            (self.canvas_width - self.matches_list_x, self.canvas_height),
            GUIConstants.BACKGROUND_COLOR,
        )
        draw = ImageDraw.Draw(img)

        word_indent = GUIConstants.COMPONENT_PADDING

        highlighted_row = 3
        num_possible_rows = 11
        y = (
            self.highlighted_row_y
            - GUIConstants.LIST_ITEM_PADDING
            - 3 * self.matches_list_row_height
        )

        if not highlight_word:
            list_starting_index = self.selected_possible_words_index - highlighted_row
            for row, i in enumerate(
                range(list_starting_index, list_starting_index + num_possible_rows)
            ):
                if i < 0:
                    # We're near the top of the list, not enough items to fill above the highlighted row
                    continue

                if row == highlighted_row:
                    # Leave the highlighted row to be rendered below
                    continue

                if len(self.possible_words) <= i:
                    # No more possible words to render
                    break

                if row < highlighted_row:
                    self.cur_y = (
                        self.highlighted_row_y
                        - GUIConstants.COMPONENT_PADDING
                        - (highlighted_row - row - 1) * self.matches_list_row_height
                    )

                elif row > highlighted_row:
                    self.cur_y = (
                        self.highlighted_row_y
                        + self.matches_list_highlight_button.height
                        + (row - highlighted_row) * self.matches_list_row_height
                    )

                # else draw the nth row
                draw.text(
                    (word_indent, self.cur_y),
                    self.possible_words[i],
                    fill="#ddd",
                    font=self.word_font,
                    anchor="ls",
                )

        self.canvas.paste(
            img.crop((0, self.top_nav.height, img.width, img.height)),
            (self.matches_list_x, self.matches_list_y),
        )

        # Now render the buttons over the matches list
        self.matches_list_highlight_button.text = self.possible_words[
            self.selected_possible_words_index
        ]
        self.matches_list_highlight_button.is_selected = True
        self.matches_list_highlight_button.render()

        self.matches_list_up_button.render()
        self.matches_list_down_button.render()

    def _render(self):
        super()._render()
        self.keyboard.render_keys()
        self.text_entry_display.render()
        self.render_possible_matches()

        self.renderer.show_image()

    def _run(self):
        while True:
            input = self.hw_inputs.wait_for(HardwareButtonsConstants.ALL_KEYS)

            with self.renderer.lock:
                if self.is_input_in_top_nav:
                    if input == HardwareButtonsConstants.KEY_PRESS:
                        # User clicked the "back" arrow
                        return RET_CODE__BACK_BUTTON

                    elif input == HardwareButtonsConstants.KEY_UP:
                        input = Keyboard.ENTER_BOTTOM
                        self.is_input_in_top_nav = False
                        # Re-render it without the highlight
                        self.top_nav.left_button.is_selected = False
                        self.top_nav.left_button.render()

                    elif input == HardwareButtonsConstants.KEY_DOWN:
                        input = Keyboard.ENTER_TOP
                        self.is_input_in_top_nav = False
                        # Re-render it without the highlight
                        self.top_nav.left_button.is_selected = False
                        self.top_nav.left_button.render()

                    elif input in [
                        HardwareButtonsConstants.KEY_RIGHT,
                        HardwareButtonsConstants.KEY_LEFT,
                    ]:
                        # no action in this context
                        continue

                ret_val = self.keyboard.update_from_input(input)

                if ret_val in Keyboard.EXIT_DIRECTIONS:
                    self.is_input_in_top_nav = True
                    self.top_nav.left_button.is_selected = True
                    self.top_nav.left_button.render()

                elif ret_val in Keyboard.ADDITIONAL_KEYS:
                    if (
                        input == HardwareButtonsConstants.KEY_PRESS
                        and ret_val == Keyboard.KEY_BACKSPACE["code"]
                    ):
                        self.letters = self.letters[:-2]
                        self.letters.append(" ")

                        # Reactivate keys after deleting last letter
                        self.calc_possible_alphabet()
                        self.keyboard.update_active_keys(
                            active_keys=self.possible_alphabet
                        )
                        self.keyboard.render_keys()

                        # Update the right-hand possible matches area
                        self.render_possible_matches()

                    elif ret_val == Keyboard.KEY_BACKSPACE["code"]:
                        # We're just hovering over DEL but haven't clicked. Show blank (" ")
                        #   in the live text entry display at the top.
                        self.letters = self.letters[:-1]
                        self.letters.append(" ")

                # Has the user made a final selection of a candidate word?
                final_selection = None
                if input == HardwareButtonsConstants.KEY1 and self.possible_words:
                    # Scroll the list up
                    self.selected_possible_words_index -= 1
                    if self.selected_possible_words_index < 0:
                        self.selected_possible_words_index = 0

                    if not self.arrow_up_is_active:
                        # Flash the up arrow as selected
                        self.arrow_up_is_active = True
                        self.matches_list_up_button.is_selected = True

                elif input == HardwareButtonsConstants.KEY2:
                    if self.possible_words:
                        final_selection = self.possible_words[
                            self.selected_possible_words_index
                        ]

                elif input == HardwareButtonsConstants.KEY3 and self.possible_words:
                    # Scroll the list down
                    self.selected_possible_words_index += 1
                    if self.selected_possible_words_index >= len(self.possible_words):
                        self.selected_possible_words_index = (
                            len(self.possible_words) - 1
                        )

                    if not self.arrow_down_is_active:
                        # Flash the down arrow as selected
                        self.arrow_down_is_active = True
                        self.matches_list_down_button.is_selected = True

                if (
                    input is not HardwareButtonsConstants.KEY1
                    and self.arrow_up_is_active
                ):
                    # Deactivate the UP arrow and redraw
                    self.arrow_up_is_active = False
                    self.matches_list_up_button.is_selected = False

                if (
                    input is not HardwareButtonsConstants.KEY3
                    and self.arrow_down_is_active
                ):
                    # Deactivate the DOWN arrow and redraw
                    self.arrow_down_is_active = False
                    self.matches_list_down_button.is_selected = False

                if final_selection:
                    # Animate the selection storage, then return the word to the caller
                    self.letters = list(final_selection + " ")
                    self.render_possible_matches(highlight_word=final_selection)
                    self.text_entry_display.cur_text = "".join(self.letters)
                    self.text_entry_display.render()
                    self.renderer.show_image()

                    return final_selection

                elif (
                    input == HardwareButtonsConstants.KEY_PRESS
                    and ret_val in self.possible_alphabet
                ):
                    # User has locked in the current letter
                    if self.letters[-1] != " ":
                        # We'll save that locked in letter next but for now update the
                        # live text entry display with blank (" ") so that we don't try
                        # to autocalc matches against a second copy of the letter they
                        # just selected. e.g. They KEY_PRESS on "s" to build "mus". If
                        # we advance the live block cursor AND display "s" in it, the
                        # current word would then be "muss" with no matches. If "mus"
                        # can get us to our match, we don't want it to disappear right
                        # as we KEY_PRESS.
                        self.letters.append(" ")
                    else:
                        # clicked same letter twice in a row. Because of the above, an
                        # immediate second click of the same letter would lock in "ap "
                        # (note the space) instead of "app". So we replace that trailing
                        # space with the correct repeated letter and then, as above,
                        # append a trailing blank.
                        self.letters = self.letters[:-1]
                        self.letters.append(ret_val)
                        self.letters.append(" ")

                    # Recalc and deactivate keys after advancing
                    self.calc_possible_alphabet()
                    self.keyboard.update_active_keys(active_keys=self.possible_alphabet)

                    if len(self.possible_alphabet) == 1:
                        # If there's only one possible letter left, select it
                        self.keyboard.set_selected_key(self.possible_alphabet[0])

                    self.keyboard.render_keys()

                elif (
                    input in HardwareButtonsConstants.KEYS__LEFT_RIGHT_UP_DOWN
                    or input in (Keyboard.ENTER_TOP, Keyboard.ENTER_BOTTOM)
                ):
                    if ret_val in self.possible_alphabet:
                        # Live joystick movement; haven't locked this new letter in yet.
                        # Replace the last letter w/the currently selected one. But don't
                        # call `calc_possible_alphabet()` because we want to still be able
                        # to freely float to a different letter; only update the active
                        # keyboard keys when a selection has been locked in (KEY_PRESS) or
                        # removed ("del").
                        self.letters = self.letters[:-1]
                        self.letters.append(ret_val)
                        self.calc_possible_words()  # live update our matches as we move

                    else:
                        # We've navigated to a deactivated letter
                        pass

                # Render the text entry display and cursor block
                self.text_entry_display.cur_text = "".join(self.letters)
                self.text_entry_display.render()

                # Update the right-hand possible matches area
                self.render_possible_matches()

                # Now issue one call to send the pixels to the screen
                self.renderer.show_image()


@dataclass
class SeedFinalizeScreen(ButtonListScreen):
    fingerprint: str = None
    is_bottom_list: bool = True
    button_data: list = None

    def __post_init__(self):
        self.show_back_button = False
        super().__post_init__()

        self.fingerprint_icontl = IconTextLine(
            icon_name=SeedSignerIconConstants.FINGERPRINT,
            icon_color=GUIConstants.INFO_COLOR,
            icon_size=GUIConstants.ICON_FONT_SIZE + 12,
            label_text=_("fingerprint"),
            value_text=self.fingerprint,
            font_size=GUIConstants.BODY_FONT_SIZE + 2,
            is_text_centered=True,
            screen_y=int((self.buttons[0].screen_y) / 2) + 18,
        )
        self.components.append(self.fingerprint_icontl)


@dataclass
class SeedOptionsScreen(ButtonListScreen):
    fingerprint: str = None
    is_bottom_list: bool = True

    def __post_init__(self):
        self.is_button_text_centered = False
        super().__post_init__()

        self.button = IconButton(
            text=self.fingerprint,
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=GUIConstants.EDGE_PADDING,
            icon_name=SeedSignerIconConstants.FINGERPRINT,
            icon_size=GUIConstants.ICON_FONT_SIZE + 12,
            is_text_centered=True,
            is_icon_inline=True,
            width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
            background_color=GUIConstants.BACKGROUND_COLOR,
        )
        self.components.append(self.button)


@dataclass
class SeedWordsScreen(WarningEdgesMixin, ButtonListScreen):
    words: List[str] = None
    page_index: int = 0
    num_pages: int = 3
    is_bottom_list: bool = True
    status_color: str = GUIConstants.DIRE_WARNING_COLOR

    def __post_init__(self):
        # TRANSLATOR_NOTE: Displays the page number and total: (e.g. page 1 of 6)
        self.title = _("Seed Words: {}/{}").format(self.page_index + 1, self.num_pages)
        super().__post_init__()

        words_per_page = len(self.words)

        self.body_x = 0
        self.body_y = self.top_nav.height - int(GUIConstants.COMPONENT_PADDING / 2)
        self.body_height = self.buttons[0].screen_y - self.body_y

        # Have to supersample the whole body since it's all at the small font size
        supersampling_factor = 1
        font = Fonts.get_font(
            GUIConstants.BODY_FONT_NAME,
            (GUIConstants.TOP_NAV_TITLE_FONT_SIZE + 2) * supersampling_factor,
        )

        # Calc horizontal center based on longest word
        max_word_width = 0
        for word in self.words:
            (left, top, right, bottom) = font.getbbox(word, anchor="ls")
            if right > max_word_width:
                max_word_width = right

        # Measure the max digit height for the numbering boxes, from baseline
        number_font = Fonts.get_font(
            GUIConstants.BODY_FONT_NAME,
            GUIConstants.BUTTON_FONT_SIZE * supersampling_factor,
        )
        (left, top, right, bottom) = number_font.getbbox("24", anchor="ls")
        number_height = -1 * top
        number_width = right
        number_box_width = number_width + int(
            GUIConstants.COMPONENT_PADDING / 2 * supersampling_factor
        )
        number_box_height = number_box_width

        number_box_x = (
            int(
                (
                    self.canvas_width * supersampling_factor
                    - number_box_width
                    - GUIConstants.COMPONENT_PADDING * supersampling_factor
                    - max_word_width
                )
            )
            / 2
        )
        number_box_y = GUIConstants.COMPONENT_PADDING * supersampling_factor

        # Set up our temp supersampled rendering surface
        self.body_img = Image.new(
            "RGB",
            (
                self.canvas_width * supersampling_factor,
                self.body_height * supersampling_factor,
            ),
            GUIConstants.BACKGROUND_COLOR,
        )
        draw = ImageDraw.Draw(self.body_img)

        for index, word in enumerate(self.words):
            draw.rounded_rectangle(
                (
                    number_box_x,
                    number_box_y,
                    number_box_x + number_box_width,
                    number_box_y + number_box_height,
                ),
                fill=GUIConstants.BUTTON_BACKGROUND_COLOR,
                radius=5 * supersampling_factor,
            )
            baseline_y = (
                number_box_y
                + number_box_height
                - int((number_box_height - number_height) / 2)
            )
            draw.text(
                (number_box_x + int(number_box_width / 2), baseline_y),
                font=number_font,
                text=str(self.page_index * words_per_page + index + 1),
                fill=GUIConstants.INFO_COLOR,
                anchor="ms",  # Middle (centered), baSeline
            )

            # Now draw the word
            draw.text(
                (
                    number_box_x
                    + number_box_width
                    + (GUIConstants.COMPONENT_PADDING * supersampling_factor),
                    baseline_y,
                ),
                font=font,
                text=word,
                fill=GUIConstants.BODY_FONT_COLOR,
                anchor="ls",  # Left, baSeline
            )

            number_box_y += number_box_height + (
                int(1.5 * GUIConstants.COMPONENT_PADDING) * supersampling_factor
            )

        # Resize to target and sharpen final image
        self.body_img = self.body_img.resize(
            (self.canvas_width, self.body_height), Image.Resampling.LANCZOS
        )
        self.body_img = self.body_img.filter(ImageFilter.SHARPEN)
        self.paste_images.append((self.body_img, (self.body_x, self.body_y)))


@dataclass
class SeedBIP85SelectChildIndexScreen(KeyboardScreen):
    def __post_init__(self):
        self.title = _("BIP-85 Index")
        self.user_input = ""

        # Specify the keys in the keyboard
        self.rows = 3
        self.cols = 5
        self.keys_charset = "0123456789"
        self.show_save_button = True

        super().__post_init__()


@dataclass
class SeedWordsBackupTestPromptScreen(ButtonListScreen):
    def __post_init__(self):
        self.title = _("Verify Backup?")
        self.show_back_button = False
        self.is_bottom_list = True
        super().__post_init__()

        self.components.append(
            TextArea(
                text=_("Optionally verify that your mnemonic backup is correct."),
                screen_y=self.top_nav.height,
                is_text_centered=True,
            )
        )


@dataclass
class SeedExportXpubCustomDerivationScreen(KeyboardScreen):
    def __post_init__(self):
        self.title = _("Derivation Path")
        self.user_input = "m/"

        # Specify the keys in the keyboard
        self.rows = 3
        self.cols = 6
        self.keys_charset = "/'0123456789"
        self.show_save_button = True

        super().__post_init__()


@dataclass
class SeedExportXpubDetailsScreen(WarningEdgesMixin, ButtonListScreen):
    # Customize defaults
    is_bottom_list: bool = True
    fingerprint: str = None
    has_passphrase: bool = False
    derivation_path: str = "m/84'/0'/0'"
    xpub: str = "zpub6r..."

    def __post_init__(self):
        # Programmatically set up other args
        self.button_data = [ButtonOption("Export Xpub")]
        self.title = _("Xpub Details")

        # Initialize the base class
        super().__post_init__()

        # Set up the fingerprint and passphrase displays
        self.fingerprint_line = IconTextLine(
            icon_name=SeedSignerIconConstants.FINGERPRINT,
            icon_color=GUIConstants.INFO_COLOR,
            # TRANSLATOR_NOTE: Short for "BIP32 Master Fingerprint"
            label_text=_("Fingerprint"),
            value_text=self.fingerprint,
            screen_x=GUIConstants.COMPONENT_PADDING,
            screen_y=self.top_nav.height + GUIConstants.COMPONENT_PADDING,
        )
        self.components.append(self.fingerprint_line)

        self.derivation_line = IconTextLine(
            icon_name=SeedSignerIconConstants.DERIVATION,
            icon_color=GUIConstants.INFO_COLOR,
            # TRANSLATOR_NOTE: Short for "Derivation Path"
            label_text=_("Derivation"),
            value_text=self.derivation_path,
            screen_x=GUIConstants.COMPONENT_PADDING,
            screen_y=self.components[-1].screen_y
            + self.components[-1].height
            + int(1.5 * GUIConstants.COMPONENT_PADDING),
        )
        self.components.append(self.derivation_line)

        font_name = GUIConstants.FIXED_WIDTH_FONT_NAME
        font_size = GUIConstants.BODY_FONT_SIZE + 2
        left, top, right, bottom = Fonts.get_font(font_name, font_size).getbbox("X")
        char_width = right - left
        num_chars = (
            int(
                (
                    self.canvas_width
                    - GUIConstants.ICON_FONT_SIZE
                    - 2 * GUIConstants.COMPONENT_PADDING
                )
                / char_width
            )
            - 3
        )  # ellipsis

        self.xpub_line = IconTextLine(
            icon_name=FontAwesomeIconConstants.X,
            icon_color=GUIConstants.INFO_COLOR,
            label_text=_("Xpub"),
            value_text=f"{self.xpub[:num_chars]}...",
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE + 2,
            screen_x=GUIConstants.COMPONENT_PADDING,
            screen_y=self.components[-1].screen_y
            + self.components[-1].height
            + int(1.5 * GUIConstants.COMPONENT_PADDING),
        )
        self.components.append(self.xpub_line)


@dataclass
class SeedAddPassphraseScreen(BaseTopNavScreen):
    passphrase: str = ""

    # Only used by the screenshot generator
    initial_keyboard: str = None

    KEYBOARD__LOWERCASE_BUTTON_TEXT = "abc"
    KEYBOARD__UPPERCASE_BUTTON_TEXT = "ABC"
    KEYBOARD__DIGITS_BUTTON_TEXT = "123"
    KEYBOARD__SYMBOLS_1_BUTTON_TEXT = "!@#"
    KEYBOARD__SYMBOLS_2_BUTTON_TEXT = "*[]"

    def __post_init__(self):
        super().__post_init__()

        keys_lower = "abcdefghijklmnopqrstuvwxyz"
        keys_upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        keys_number = "0123456789"

        # Present the most common/puncutation-related symbols & the most human-friendly
        #   symbols first (limited to 18 chars).
        keys_symbol_1 = """!@#$%&();:,.-+='"?"""

        # Isolate the more math-oriented or just uncommon symbols
        keys_symbol_2 = """^*[]{}_\\|<>/`~"""

        # Set up the keyboard params
        self.right_panel_buttons_width = 56

        max_cols = 9
        text_entry_display_y = self.top_nav.height
        text_entry_display_height = 30

        keyboard_start_y = (
            text_entry_display_y
            + text_entry_display_height
            + GUIConstants.COMPONENT_PADDING
        )
        self.keyboard_abc = Keyboard(
            draw=self.renderer.draw,
            charset=keys_lower,
            rows=4,
            cols=max_cols,
            rect=(
                GUIConstants.COMPONENT_PADDING,
                keyboard_start_y,
                self.canvas_width
                - GUIConstants.COMPONENT_PADDING
                - self.right_panel_buttons_width,
                self.canvas_height - GUIConstants.EDGE_PADDING,
            ),
            additional_keys=[
                Keyboard.KEY_SPACE_5,
                Keyboard.KEY_CURSOR_LEFT,
                Keyboard.KEY_CURSOR_RIGHT,
                Keyboard.KEY_BACKSPACE,
            ],
            auto_wrap=[Keyboard.WRAP_LEFT, Keyboard.WRAP_RIGHT],
        )

        self.keyboard_ABC = Keyboard(
            draw=self.renderer.draw,
            charset=keys_upper,
            rows=4,
            cols=max_cols,
            rect=(
                GUIConstants.COMPONENT_PADDING,
                keyboard_start_y,
                self.canvas_width
                - GUIConstants.COMPONENT_PADDING
                - self.right_panel_buttons_width,
                self.canvas_height - GUIConstants.EDGE_PADDING,
            ),
            additional_keys=[
                Keyboard.KEY_SPACE_5,
                Keyboard.KEY_CURSOR_LEFT,
                Keyboard.KEY_CURSOR_RIGHT,
                Keyboard.KEY_BACKSPACE,
            ],
            auto_wrap=[Keyboard.WRAP_LEFT, Keyboard.WRAP_RIGHT],
            render_now=False,
        )

        self.keyboard_digits = Keyboard(
            draw=self.renderer.draw,
            charset=keys_number,
            rows=3,
            cols=5,
            rect=(
                GUIConstants.COMPONENT_PADDING,
                keyboard_start_y,
                self.canvas_width
                - GUIConstants.COMPONENT_PADDING
                - self.right_panel_buttons_width,
                self.canvas_height - GUIConstants.EDGE_PADDING,
            ),
            additional_keys=[
                Keyboard.KEY_CURSOR_LEFT,
                Keyboard.KEY_CURSOR_RIGHT,
                Keyboard.KEY_BACKSPACE,
            ],
            auto_wrap=[Keyboard.WRAP_LEFT, Keyboard.WRAP_RIGHT],
            render_now=False,
        )

        self.keyboard_symbols_1 = Keyboard(
            draw=self.renderer.draw,
            charset=keys_symbol_1,
            rows=4,
            cols=6,
            rect=(
                GUIConstants.COMPONENT_PADDING,
                keyboard_start_y,
                self.canvas_width
                - GUIConstants.COMPONENT_PADDING
                - self.right_panel_buttons_width,
                self.canvas_height - GUIConstants.EDGE_PADDING,
            ),
            additional_keys=[
                Keyboard.KEY_SPACE_2,
                Keyboard.KEY_CURSOR_LEFT,
                Keyboard.KEY_CURSOR_RIGHT,
                Keyboard.KEY_BACKSPACE,
            ],
            auto_wrap=[Keyboard.WRAP_LEFT, Keyboard.WRAP_RIGHT],
            render_now=False,
        )

        self.keyboard_symbols_2 = Keyboard(
            draw=self.renderer.draw,
            charset=keys_symbol_2,
            rows=4,
            cols=6,
            rect=(
                GUIConstants.COMPONENT_PADDING,
                keyboard_start_y,
                self.canvas_width
                - GUIConstants.COMPONENT_PADDING
                - self.right_panel_buttons_width,
                self.canvas_height - GUIConstants.EDGE_PADDING,
            ),
            additional_keys=[
                Keyboard.KEY_SPACE_2,
                Keyboard.KEY_CURSOR_LEFT,
                Keyboard.KEY_CURSOR_RIGHT,
                Keyboard.KEY_BACKSPACE,
            ],
            auto_wrap=[Keyboard.WRAP_LEFT, Keyboard.WRAP_RIGHT],
            render_now=False,
        )

        self.text_entry_display = TextEntryDisplay(
            canvas=self.renderer.canvas,
            rect=(
                GUIConstants.EDGE_PADDING,
                text_entry_display_y,
                self.canvas_width - self.right_panel_buttons_width,
                text_entry_display_y + text_entry_display_height,
            ),
            cursor_mode=TextEntryDisplay.CURSOR_MODE__BAR,
            is_centered=False,
            cur_text="".join(self.passphrase),
        )

        # Nudge the buttons off the right edge w/padding
        hw_button_x = (
            self.canvas_width
            - self.right_panel_buttons_width
            + GUIConstants.COMPONENT_PADDING
        )

        # Calc center button position first
        hw_button_y = int((self.canvas_height - GUIConstants.BUTTON_HEIGHT) / 2)

        self.hw_button1 = Button(
            text=self.KEYBOARD__UPPERCASE_BUTTON_TEXT,
            is_text_centered=False,
            font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 4,
            width=self.right_panel_buttons_width,
            screen_x=hw_button_x,
            screen_y=hw_button_y
            - 3 * GUIConstants.COMPONENT_PADDING
            - GUIConstants.BUTTON_HEIGHT,
            is_scrollable_text=False,
        )

        self.hw_button2 = Button(
            text=self.KEYBOARD__DIGITS_BUTTON_TEXT,
            is_text_centered=False,
            font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 4,
            width=self.right_panel_buttons_width,
            screen_x=hw_button_x,
            screen_y=hw_button_y,
            is_scrollable_text=False,
        )

        self.hw_button3 = IconButton(
            icon_name=SeedSignerIconConstants.CHECK,
            icon_color=GUIConstants.SUCCESS_COLOR,
            width=self.right_panel_buttons_width,
            screen_x=hw_button_x,
            screen_y=hw_button_y
            + 3 * GUIConstants.COMPONENT_PADDING
            + GUIConstants.BUTTON_HEIGHT,
            is_scrollable_text=False,
        )

    def _render(self):
        super()._render()

        # Change from the default lowercase keyboard for the screenshot generator
        if self.initial_keyboard == self.KEYBOARD__UPPERCASE_BUTTON_TEXT:
            cur_keyboard = self.keyboard_ABC
            self.hw_button1.text = self.KEYBOARD__LOWERCASE_BUTTON_TEXT

        elif self.initial_keyboard == self.KEYBOARD__DIGITS_BUTTON_TEXT:
            cur_keyboard = self.keyboard_digits
            self.hw_button2.text = self.KEYBOARD__SYMBOLS_1_BUTTON_TEXT

        elif self.initial_keyboard == self.KEYBOARD__SYMBOLS_1_BUTTON_TEXT:
            cur_keyboard = self.keyboard_symbols_1
            self.hw_button2.text = self.KEYBOARD__SYMBOLS_2_BUTTON_TEXT

        elif self.initial_keyboard == self.KEYBOARD__SYMBOLS_2_BUTTON_TEXT:
            cur_keyboard = self.keyboard_symbols_2
            self.hw_button2.text = self.KEYBOARD__DIGITS_BUTTON_TEXT

        else:
            cur_keyboard = self.keyboard_abc

        self.text_entry_display.render()
        self.hw_button1.render()
        self.hw_button2.render()
        self.hw_button3.render()
        cur_keyboard.render_keys()

        self.renderer.show_image()

    def _run(self):
        cursor_position = len(self.passphrase)
        cur_keyboard = self.keyboard_abc
        cur_button1_text = self.KEYBOARD__UPPERCASE_BUTTON_TEXT
        cur_button2_text = self.KEYBOARD__DIGITS_BUTTON_TEXT

        # Start the interactive update loop
        while True:
            input = self.hw_inputs.wait_for(HardwareButtonsConstants.ALL_KEYS)

            keyboard_swap = False

            with self.renderer.lock:
                # Check our two possible exit conditions
                # TODO: note the unusual return value, consider refactoring to a Response object in the future
                if input == HardwareButtonsConstants.KEY3:
                    # Save!
                    # First light up key3
                    self.hw_button3.is_selected = True
                    self.hw_button3.render()
                    self.renderer.show_image()
                    return dict(passphrase=self.passphrase)

                elif (
                    input == HardwareButtonsConstants.KEY_PRESS
                    and self.top_nav.is_selected
                ):
                    # Back button clicked
                    return dict(passphrase=self.passphrase, is_back_button=True)

                # Check for keyboard swaps
                if input == HardwareButtonsConstants.KEY1:
                    # First light up key1
                    self.hw_button1.is_selected = True
                    self.hw_button1.render()

                    # Return to the same button2 keyboard, if applicable
                    if cur_keyboard == self.keyboard_digits:
                        cur_button2_text = self.KEYBOARD__DIGITS_BUTTON_TEXT
                    elif cur_keyboard == self.keyboard_symbols_1:
                        cur_button2_text = self.KEYBOARD__SYMBOLS_1_BUTTON_TEXT
                    elif cur_keyboard == self.keyboard_symbols_2:
                        cur_button2_text = self.KEYBOARD__SYMBOLS_2_BUTTON_TEXT

                    if cur_button1_text == self.KEYBOARD__LOWERCASE_BUTTON_TEXT:
                        self.keyboard_abc.set_selected_key_indices(
                            x=cur_keyboard.selected_key["x"],
                            y=cur_keyboard.selected_key["y"],
                        )
                        cur_keyboard = self.keyboard_abc
                        cur_button1_text = self.KEYBOARD__UPPERCASE_BUTTON_TEXT
                    else:
                        self.keyboard_ABC.set_selected_key_indices(
                            x=cur_keyboard.selected_key["x"],
                            y=cur_keyboard.selected_key["y"],
                        )
                        cur_keyboard = self.keyboard_ABC
                        cur_button1_text = self.KEYBOARD__LOWERCASE_BUTTON_TEXT
                    cur_keyboard.render_keys()

                    # Show the changes; this loop will have two renders
                    self.renderer.show_image()

                    keyboard_swap = True
                    ret_val = None

                elif input == HardwareButtonsConstants.KEY2:
                    # First light up key2
                    self.hw_button2.is_selected = True
                    self.hw_button2.render()
                    self.renderer.show_image()

                    # And reset for next redraw
                    self.hw_button2.is_selected = False

                    # Return to the same button1 keyboard, if applicable
                    if cur_keyboard == self.keyboard_abc:
                        cur_button1_text = self.KEYBOARD__LOWERCASE_BUTTON_TEXT
                    elif cur_keyboard == self.keyboard_ABC:
                        cur_button1_text = self.KEYBOARD__UPPERCASE_BUTTON_TEXT

                    if cur_button2_text == self.KEYBOARD__DIGITS_BUTTON_TEXT:
                        self.keyboard_digits.set_selected_key_indices(
                            x=cur_keyboard.selected_key["x"],
                            y=cur_keyboard.selected_key["y"],
                        )
                        cur_keyboard = self.keyboard_digits
                        cur_keyboard.render_keys()
                        cur_button2_text = self.KEYBOARD__SYMBOLS_1_BUTTON_TEXT
                    elif cur_button2_text == self.KEYBOARD__SYMBOLS_1_BUTTON_TEXT:
                        self.keyboard_symbols_1.set_selected_key_indices(
                            x=cur_keyboard.selected_key["x"],
                            y=cur_keyboard.selected_key["y"],
                        )
                        cur_keyboard = self.keyboard_symbols_1
                        cur_keyboard.render_keys()
                        cur_button2_text = self.KEYBOARD__SYMBOLS_2_BUTTON_TEXT
                    elif cur_button2_text == self.KEYBOARD__SYMBOLS_2_BUTTON_TEXT:
                        self.keyboard_symbols_2.set_selected_key_indices(
                            x=cur_keyboard.selected_key["x"],
                            y=cur_keyboard.selected_key["y"],
                        )
                        cur_keyboard = self.keyboard_symbols_2
                        cur_keyboard.render_keys()
                        cur_button2_text = self.KEYBOARD__DIGITS_BUTTON_TEXT
                    cur_keyboard.render_keys()

                    # Show the changes; this loop will have two renders
                    self.renderer.show_image()

                    keyboard_swap = True
                    ret_val = None

                else:
                    # Process normal input
                    if (
                        input
                        in [
                            HardwareButtonsConstants.KEY_UP,
                            HardwareButtonsConstants.KEY_DOWN,
                        ]
                        and self.top_nav.is_selected
                    ):
                        # We're navigating off the previous button
                        self.top_nav.is_selected = False
                        self.top_nav.render_buttons()

                        # Override the actual input w/an ENTER signal for the Keyboard
                        if input == HardwareButtonsConstants.KEY_DOWN:
                            input = Keyboard.ENTER_TOP
                        else:
                            input = Keyboard.ENTER_BOTTOM
                    elif (
                        input
                        in [
                            HardwareButtonsConstants.KEY_LEFT,
                            HardwareButtonsConstants.KEY_RIGHT,
                        ]
                        and self.top_nav.is_selected
                    ):
                        # ignore
                        continue

                    ret_val = cur_keyboard.update_from_input(input)

                # Now process the result from the keyboard
                if ret_val in Keyboard.EXIT_DIRECTIONS:
                    self.top_nav.is_selected = True
                    self.top_nav.render_buttons()

                elif (
                    ret_val in Keyboard.ADDITIONAL_KEYS
                    and input == HardwareButtonsConstants.KEY_PRESS
                ):
                    if ret_val == Keyboard.KEY_BACKSPACE["code"]:
                        if cursor_position == 0:
                            pass
                        elif cursor_position == len(self.passphrase):
                            self.passphrase = self.passphrase[:-1]
                            cursor_position -= 1
                        else:
                            self.passphrase = (
                                self.passphrase[: cursor_position - 1]
                                + self.passphrase[cursor_position:]
                            )
                            cursor_position -= 1

                    elif ret_val == Keyboard.KEY_CURSOR_LEFT["code"]:
                        cursor_position -= 1
                        if cursor_position < 0:
                            cursor_position = 0

                    elif ret_val == Keyboard.KEY_CURSOR_RIGHT["code"]:
                        cursor_position += 1
                        if cursor_position > len(self.passphrase):
                            cursor_position = len(self.passphrase)

                    elif ret_val == Keyboard.KEY_SPACE["code"]:
                        if cursor_position == len(self.passphrase):
                            self.passphrase += " "
                        else:
                            self.passphrase = (
                                self.passphrase[:cursor_position]
                                + " "
                                + self.passphrase[cursor_position:]
                            )
                        cursor_position += 1

                    # Update the text entry display and cursor
                    self.text_entry_display.render(self.passphrase, cursor_position)

                elif (
                    input == HardwareButtonsConstants.KEY_PRESS
                    and ret_val not in Keyboard.ADDITIONAL_KEYS
                ):
                    # User has locked in the current letter
                    if cursor_position == len(self.passphrase):
                        self.passphrase += ret_val
                    else:
                        self.passphrase = (
                            self.passphrase[:cursor_position]
                            + ret_val
                            + self.passphrase[cursor_position:]
                        )
                    cursor_position += 1

                    # Update the text entry display and cursor
                    self.text_entry_display.render(self.passphrase, cursor_position)

                elif (
                    input in HardwareButtonsConstants.KEYS__LEFT_RIGHT_UP_DOWN
                    or keyboard_swap
                ):
                    # Live joystick movement; haven't locked this new letter in yet.
                    # Leave current spot blank for now. Only update the active keyboard keys
                    # when a selection has been locked in (KEY_PRESS) or removed ("del").
                    pass

                if keyboard_swap:
                    # Show the hw buttons' updated text and not active state
                    self.hw_button1.text = cur_button1_text
                    self.hw_button2.text = cur_button2_text
                    self.hw_button1.is_selected = False
                    self.hw_button2.is_selected = False
                    self.hw_button1.render()
                    self.hw_button2.render()

                self.renderer.show_image()


@dataclass
class SeedReviewPassphraseScreen(ButtonListScreen):
    fingerprint_without: str = None
    fingerprint_with: str = None
    passphrase: str = None

    def __post_init__(self):
        # Customize defaults
        self.title = _("Verify Passphrase")
        self.is_bottom_list = True

        super().__post_init__()

        self.components.append(
            IconTextLine(
                icon_name=SeedSignerIconConstants.FINGERPRINT,
                icon_color=GUIConstants.INFO_COLOR,
                # TRANSLATOR_NOTE: Describes the effect of applying a BIP-39 passphrase; it changes the seed's fingerprint
                label_text=_("changes fingerprint"),
                value_text=f"{self.fingerprint_without} >> {self.fingerprint_with}",
                is_text_centered=True,
                screen_y=self.buttons[0].screen_y
                - GUIConstants.COMPONENT_PADDING
                - int(GUIConstants.BODY_FONT_SIZE * 2.5),
            )
        )

        if self.passphrase != self.passphrase.strip() or "  " in self.passphrase:
            self.passphrase = self.passphrase.replace(" ", "\u2589")
        available_height = (
            self.components[-1].screen_y
            - GUIConstants.TOP_NAV_HEIGHT
            + GUIConstants.COMPONENT_PADDING
        )
        max_font_size = GUIConstants.TOP_NAV_TITLE_FONT_SIZE + 8
        min_font_size = GUIConstants.TOP_NAV_TITLE_FONT_SIZE - 4
        font_size = max_font_size
        max_lines = 3
        passphrase = [self.passphrase]
        found_solution = False
        for font_size in range(max_font_size, min_font_size, -2):
            if found_solution:
                break
            font = Fonts.get_font(
                font_name=GUIConstants.FIXED_WIDTH_FONT_NAME, size=font_size
            )
            left, top, right, bottom = font.getbbox("X")
            char_width, char_height = right - left, bottom - top
            for num_lines in range(1, max_lines + 1):
                # Break the passphrase into n lines
                chars_per_line = math.ceil(len(self.passphrase) / num_lines)
                passphrase = []
                for i in range(0, len(self.passphrase), chars_per_line):
                    passphrase.append(self.passphrase[i : i + chars_per_line])

                # See if it fits in this configuration
                if (
                    char_width * len(passphrase[0])
                    <= self.canvas_width - 2 * GUIConstants.EDGE_PADDING
                ):
                    # Width is good...
                    if num_lines * char_height <= available_height:
                        # And the height is good!
                        found_solution = True
                        break

        # Set up each line of text
        screen_y = (
            GUIConstants.TOP_NAV_HEIGHT
            + int((available_height - char_height * num_lines) / 2)
            - GUIConstants.COMPONENT_PADDING
        )
        for line in passphrase:
            self.components.append(
                TextArea(
                    text=line,
                    font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
                    font_size=font_size,
                    font_color="orange",
                    is_text_centered=True,
                    screen_y=screen_y,
                    allow_text_overflow=True,
                )
            )
            screen_y += char_height + 2


# QR Code Screen
@dataclass
class QRCodeScreen(WarningEdgesMixin, ButtonListScreen):
    qr_data: str = None

    def __post_init__(self):

        back_button = ButtonOption(_("Back"), SeedSignerIconConstants.BACK)

        self.button_data = [back_button]
        self.is_bottom_list = True
        super().__post_init__()

        # qr_image = QR().qrimage(data=self.qr_data).convert("RGBA")
        qr_img = qrcode.make(self.qr_data)
        qr_img = qr_img.convert("RGB")
        qr_img = qr_img.resize((140, 140), Image.LANCZOS)
        qr_image = qr_img

        x_cord = (self.canvas_width - GUIConstants.QR_WIDTH) // 2

        self.paste_images.append((qr_image, (x_cord, GUIConstants.EDGE_PADDING // 2)))

        self.components.append(
            TextArea(
                text=self.qr_data,
                font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
                font_size=11,
                is_text_centered=True,
                auto_line_break=True,
                treat_chars_as_words=True,
                allow_text_overflow=True,
                screen_y=GUIConstants.QR_HEIGHT + GUIConstants.EDGE_PADDING,
                screen_x=GUIConstants.EDGE_PADDING,
            )
        )

    def _run(self):
        # Wait for the user to press the back button
        while True:
            user_input = self.hw_inputs.wait_for(
                HardwareButtonsConstants.KEYS__ANYCLICK
            )

            if user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                return RET_CODE__BACK_BUTTON  # User confirmed the seed words


# the seed generation address screen has radio buttons for selecting the address type and one input field for entering index
# types legacy and cashaddress are supported


@dataclass
class SeedGenerateAddressScreen(BaseTopNavScreen):
    def __post_init__(self):

        self.show_back_button = False

        super().__post_init__()

        #
        self.title_text = "Introduce Address Index"

        # Track the selected address type (default to Legacy)
        self.address_type = "legacy"

        # Store the user's input index
        self.user_input = ""

        # add title text
        self.title_text_display = TextArea(
            text=self.title_text,
            screen_x=GUIConstants.COMPONENT_PADDING,
            screen_y=GUIConstants.COMPONENT_PADDING * 2,
        )

        # Set up the keyboard params
        self.right_panel_buttons_width = 110

        text_entry_display_y = self.top_nav.height
        text_entry_display_height = 30

        # Add text display for the entered index
        self.text_entry_display = TextEntryDisplay(
            canvas=self.renderer.canvas,
            rect=(
                GUIConstants.EDGE_PADDING,
                text_entry_display_y,
                self.canvas_width
                - self.right_panel_buttons_width
                - GUIConstants.EDGE_PADDING,
                text_entry_display_y + text_entry_display_height,
            ),
            cursor_mode=TextEntryDisplay.CURSOR_MODE__BAR,
            is_centered=False,
            cur_text="".join(self.user_input),
        )

        keyboard_start_y = (
            text_entry_display_y
            + text_entry_display_height
            + GUIConstants.COMPONENT_PADDING
        )

        self.keyboard = Keyboard(
            draw=self.renderer.draw,
            charset="1234567890",
            rows=3,
            cols=4,
            rect=(
                GUIConstants.COMPONENT_PADDING,
                keyboard_start_y,
                self.canvas_width
                - GUIConstants.COMPONENT_PADDING
                - self.right_panel_buttons_width,
                self.canvas_height
                - 2 * GUIConstants.EDGE_PADDING
                - GUIConstants.BUTTON_HEIGHT,
            ),
            auto_wrap=[Keyboard.WRAP_LEFT, Keyboard.WRAP_RIGHT],
        )

        self.keyboard.render_keys()

        # Nudge the buttons off the right edge w/padding
        hw_button_x = (
            self.canvas_width
            - self.right_panel_buttons_width
            + GUIConstants.COMPONENT_PADDING
        )

        # Calc center button position first
        hw_button_y = int((self.canvas_height - GUIConstants.BUTTON_HEIGHT) / 2)

        self.hw_button1 = Button(
            text="Legacy",
            is_text_centered=False,
            font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 4,
            width=self.right_panel_buttons_width,
            screen_x=hw_button_x,
            screen_y=hw_button_y
            - 3 * GUIConstants.COMPONENT_PADDING
            - GUIConstants.BUTTON_HEIGHT,
            is_scrollable_text=False,
            is_selected=True,  # Legacy is selected by default
        )

        self.hw_button2 = Button(
            text="Cashaddr",
            is_text_centered=False,
            font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 4,
            width=self.right_panel_buttons_width,
            screen_x=hw_button_x,
            screen_y=hw_button_y,
            is_scrollable_text=False,
        )

        self.hw_button3 = IconButton(
            icon_name=SeedSignerIconConstants.CHECK,
            icon_color=GUIConstants.SUCCESS_COLOR,
            width=self.right_panel_buttons_width,
            screen_x=hw_button_x,
            screen_y=hw_button_y
            + 3 * GUIConstants.COMPONENT_PADDING
            + GUIConstants.BUTTON_HEIGHT,
            is_scrollable_text=False,
        )

        self.hw_button4 = IconButton(
            text=_("Back"),
            icon_name=SeedSignerIconConstants.BACK,
            icon_color=GUIConstants.REGTEST_COLOR,
            width=self.right_panel_buttons_width,
            screen_x=GUIConstants.COMPONENT_PADDING,
            screen_y=hw_button_y
            + 4 * GUIConstants.COMPONENT_PADDING
            + 2 * GUIConstants.BUTTON_HEIGHT,
            is_scrollable_text=False,
            is_icon_inline=True,
        )

        self.components.append(self.title_text_display)
        self.components.append(self.hw_button1)
        self.components.append(self.hw_button2)
        self.components.append(self.hw_button3)
        self.components.append(self.hw_button4)

    def _render(self):
        super()._render()

        # Update button selection states
        self.hw_button1.is_selected = self.address_type == "legacy"
        self.hw_button2.is_selected = self.address_type == "cashaddr"

        # Update text display
        self.keyboard.render_keys()
        self.text_entry_display.render()

        # Render components
        for component in self.components:
            component.render()

        self.renderer.show_image()

    def _run(self):
        while True:
            input = self.hw_inputs.wait_for(HardwareButtonsConstants.ALL_KEYS)

            with self.renderer.lock:
                # Check for button presses
                if input == HardwareButtonsConstants.KEY1:
                    # Legacy button pressed
                    self.address_type = "legacy"
                    self._render()
                    continue

                elif input == HardwareButtonsConstants.KEY2:
                    # Cashaddr button pressed
                    self.address_type = "cashaddr"
                    self._render()
                    continue

                elif input == HardwareButtonsConstants.KEY3:
                    # Done button pressed
                    if not self.user_input:
                        continue  # Don't allow empty input

                    # Light up the Done button
                    self.hw_button3.is_selected = True
                    self.hw_button3.render()
                    self.renderer.show_image()

                    # Return the address type and index
                    return self.address_type, int(self.user_input)
                elif (
                    input == HardwareButtonsConstants.KEY_PRESS
                    and self.hw_button4.is_selected
                ):
                    # Back button pressed
                    return RET_CODE__BACK_BUTTON

                # Handle keyboard input
                ret_val = self.keyboard.update_from_input(input)

                if ret_val in Keyboard.EXIT_DIRECTIONS:
                    self.hw_button4.is_selected = True
                    self.hw_button4.render()

                    if (
                        input == HardwareButtonsConstants.KEY_PRESS
                        and self.hw_button4.is_selected
                    ):
                        # If the back button was pressed, return to the previous screen
                        return RET_CODE__BACK_BUTTON

                elif ret_val not in Keyboard.EXIT_DIRECTIONS:
                    # If the user navigated away, reset the selection
                    self.hw_button4.is_selected = False
                    self.selected_button = None

                    if input == HardwareButtonsConstants.KEY_PRESS:
                        if ret_val in self.keyboard.charset:
                            # Add digit to input
                            self.user_input += ret_val
                            self.text_entry_display.render(self.user_input)
                        elif ret_val == Keyboard.KEY_BACKSPACE["code"]:
                            # Remove last digit
                            self.user_input = self.user_input[:-1]
                            self.text_entry_display.render(self.user_input)

                # Update the display
                self._render()
