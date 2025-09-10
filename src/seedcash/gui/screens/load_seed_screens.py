import logging
import math

from dataclasses import dataclass
from gettext import gettext as _
from PIL import Image, ImageDraw
import qrcode

from seedcash.hardware.buttons import HardwareButtonsConstants
from seedcash.gui.components import (
    Button,
    FontAwesomeIconConstants,
    Fonts,
    IconButton,
    IconTextLine,
    SeedCashIconsConstants,
    TextArea,
    GUIConstants,
)

from seedcash.gui.keyboard import Keyboard, TextEntryDisplay
from seedcash.models import visual_hash as vh

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
class SeedCashLoadSeedScreen(BaseTopNavScreen, ButtonListScreen):
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
                        return RET_CODE__BACK_BUTTON
                    return self.selected_button

                # Write the screen updates
                self.renderer.show_image()


@dataclass
class SeedCashSeedWordsScreen(BaseScreen):
    seed_words: list = None

    def __post_init__(self):
        super().__post_init__()

        if not self.seed_words:
            self.seed_words = []

        self.word_count = len(self.seed_words)
        self.current_page = 0
        self.words_per_page = 4
        self.total_pages = (
            self.word_count + self.words_per_page - 1
        ) // self.words_per_page

        # Calculate layout for word display
        self.word_height = GUIConstants.BUTTON_HEIGHT

        # Position words below the top navigation
        self.word_y = 2 * GUIConstants.COMPONENT_PADDING
        self.word_x = 2 * GUIConstants.COMPONENT_PADDING
        self.word_width = self.canvas_width - 4 * GUIConstants.COMPONENT_PADDING

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

        # Add words for current page as non-selectable buttons
        start_index = self.current_page * self.words_per_page
        end_index = min(start_index + self.words_per_page, self.word_count)

        for i in range(start_index, end_index):
            word = self.seed_words[i]
            word_y_pos = self.word_y + (
                (i - start_index) * (self.word_height + GUIConstants.COMPONENT_PADDING)
            )

            # Add word index (1-12) before the word
            word_text = f"{i + 1:2d}. {word}"

            button = Button(
                text=word_text,
                is_text_centered=False,
                font_name=GUIConstants.BODY_FONT_NAME,
                font_size=GUIConstants.BODY_FONT_SIZE,
                screen_x=self.word_x,
                screen_y=word_y_pos,
                width=self.word_width,
                height=self.word_height,
                is_selected=False,
                background_color=GUIConstants.BUTTON_BACKGROUND_COLOR,
                font_color=GUIConstants.BUTTON_FONT_COLOR,
            )
            self.components.append(button)

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

        # Generate fingerprint image using visual hash
        fingerprint_image = vh.generate_lifehash(self.fingerprint)

        # Calculate the icon size to match the original icon size
        icon_size = GUIConstants.ICON_FONT_SIZE + 12

        # Calculate position to center the fingerprint display
        fingerprint_y = int((self.buttons[0].screen_y) / 2)

        image_x = (self.canvas_width - icon_size) // 2 - 40  # Offset to left of text

        # Create the text component for the fingerprint label and value
        self.fingerprint_icontl = IconTextLine(
            icon_name=None,  # No icon since we're using the actual image
            label_text=_("fingerprint"),
            value_text=self.fingerprint,
            font_size=GUIConstants.BODY_FONT_SIZE + 2,
            is_text_centered=True,
            screen_y=fingerprint_y,
            screen_x=(image_x - 24),
        )
        self.components.append(self.fingerprint_icontl)

        # Calculate position for the fingerprint image (to the left of the text)
        # Position it where the icon would normally be

        image_y = fingerprint_y - icon_size // 2

        # Add the fingerprint image to paste_images
        self.paste_images.append(
            (fingerprint_image.resize((icon_size, icon_size)), (image_x, image_y))
        )


@dataclass
class SeedOptionsScreen(ButtonListScreen):
    fingerprint: str = None
    is_bottom_list: bool = True

    def __post_init__(self):
        self.is_button_text_centered = False
        super().__post_init__()

        # Generate fingerprint image
        fingerprint_image = vh.generate_lifehash(self.fingerprint)

        # Calculate dimensions
        image_size = 36
        spacing = 2 * GUIConstants.COMPONENT_PADDING  # Space between text and image

        # Calculate text width to determine total width needed
        font = Fonts.get_font(GUIConstants.BODY_FONT_NAME, GUIConstants.BODY_FONT_SIZE)
        text_bbox = font.getbbox(self.fingerprint)
        text_width = text_bbox[2] - text_bbox[0]

        # Calculate total width (text + spacing + image)
        total_width = text_width + spacing + image_size

        # Calculate starting x position to center everything
        start_x = (
            self.canvas_width - total_width
        ) // 2 - GUIConstants.EDGE_PADDING // 2

        # Position text on the left
        text_x = start_x
        text_y = GUIConstants.EDGE_PADDING + (image_size // 4)
        text_component = TextArea(
            text=self.fingerprint,
            screen_x=text_x,
            screen_y=text_y,
            font_name=GUIConstants.BODY_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE,
            is_text_centered=False,
        )
        self.components.append(text_component)

        # Position image on the right (after text + spacing)
        image_x = start_x + text_width + spacing
        image_y = GUIConstants.EDGE_PADDING

        # Add the fingerprint image to paste_images
        self.paste_images.append(
            (fingerprint_image.resize((image_size, image_size)), (image_x, image_y))
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
            icon_name=SeedCashIconsConstants.FINGERPRINT,
            icon_color=GUIConstants.INFO_COLOR,
            # TRANSLATOR_NOTE: Short for "BIP32 Master Fingerprint"
            label_text=_("Fingerprint"),
            value_text=self.fingerprint,
            screen_x=GUIConstants.COMPONENT_PADDING,
            screen_y=self.top_nav.height + GUIConstants.COMPONENT_PADDING,
        )
        self.components.append(self.fingerprint_line)

        self.derivation_line = IconTextLine(
            icon_name=SeedCashIconsConstants.DERIVATION,
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
            icon_name=SeedCashIconsConstants.CHECK,
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
    passphrase: str = None

    def __post_init__(self):
        # Customize defaults
        self.is_bottom_list = True

        super().__post_init__()

        # Replace spaces with block characters for better visibility
        if self.passphrase != self.passphrase.strip() or "  " in self.passphrase:
            self.passphrase = self.passphrase.replace(" ", "\u2589")

        # Calculate available height for passphrase display
        available_height = (
            self.canvas_height
            - 4 * GUIConstants.EDGE_PADDING
            - 2 * GUIConstants.BUTTON_HEIGHT
        )

        max_font_size = GUIConstants.TOP_NAV_TITLE_FONT_SIZE + 8
        min_font_size = GUIConstants.TOP_NAV_TITLE_FONT_SIZE - 4
        font_size = max_font_size
        max_lines = 3
        passphrase = [self.passphrase]
        found_solution = False

        # Find optimal font size and line configuration
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

                # Check if it fits in this configuration
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
        screen_y = 2 * GUIConstants.EDGE_PADDING

        for line in passphrase:
            self.components.append(
                TextArea(
                    text=line,
                    font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
                    font_size=font_size,
                    font_color=GUIConstants.ACCENT_COLOR,
                    is_text_centered=True,
                    screen_y=screen_y,
                    allow_text_overflow=True,
                )
            )
            screen_y += char_height + 2 * GUIConstants.COMPONENT_PADDING


@dataclass
class QRCodeScreen(BaseScreen):
    qr_data: str = None
    qr_size: int = 180

    def __post_init__(self):
        super().__post_init__()

        self.toggle_button_width = 75
        self.back_button_width = (
            self.canvas_width - self.toggle_button_width - 3 * GUIConstants.EDGE_PADDING
        )

        self.buttons_y = (
            self.canvas_height - GUIConstants.BUTTON_HEIGHT - GUIConstants.EDGE_PADDING
        )

        # Generate QR image
        qr_img = qrcode.make(self.qr_data).convert("RGB")
        qr_img = qr_img.resize((self.qr_size, self.qr_size), Image.LANCZOS)
        x_cord = (self.canvas_width - self.qr_size) // 2

        # Initialize shared components
        self.back_button = Button(
            text=_("Back"),
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.buttons_y,
            height=GUIConstants.BUTTON_HEIGHT,
            width=self.back_button_width,
            is_selected=False,
        )

        self.toggle_button = Button(
            text="Text",
            screen_x=self.canvas_width
            - self.toggle_button_width
            - GUIConstants.EDGE_PADDING,
            screen_y=self.buttons_y,
            width=self.toggle_button_width,
            height=GUIConstants.BUTTON_HEIGHT,
            is_selected=False,
        )

        self.paste_images = [(qr_img, (x_cord, GUIConstants.EDGE_PADDING // 2))]
        self.components = [self.back_button, self.toggle_button]
        self.selected_button = 1
        self.components[self.selected_button].is_selected = True

    def _render(self):
        """Render the screen"""
        super()._render()
        for component in self.components:
            component.render()
        self.renderer.show_image()

    def _run(self):
        self._render()
        while True:
            user_input = self.hw_inputs.wait_for(
                [
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT,
                ]
                + HardwareButtonsConstants.KEYS__ANYCLICK
            )

            if user_input == HardwareButtonsConstants.KEY_LEFT:
                if self.selected_button == 1:
                    self.components[self.selected_button].is_selected = False
                    self.selected_button = 0
                    self.components[self.selected_button].is_selected = True
                    self._render()

            elif user_input == HardwareButtonsConstants.KEY_RIGHT:
                if self.selected_button == 0:
                    self.components[self.selected_button].is_selected = False
                    self.selected_button = 1
                    self.components[self.selected_button].is_selected = True
                    self._render()

            elif user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                if self.selected_button == 0:
                    return RET_CODE__BACK_BUTTON
                elif self.selected_button == 1:
                    return "SWITCH"


@dataclass
class AddressScreen(BaseScreen):
    qr_data: str = None

    def __post_init__(self):
        super().__post_init__()

        self.toggle_button_width = 75
        self.back_button_width = (
            self.canvas_width - self.toggle_button_width - 3 * GUIConstants.EDGE_PADDING
        )

        self.buttons_y = (
            self.canvas_height - GUIConstants.BUTTON_HEIGHT - GUIConstants.EDGE_PADDING
        )

        self.qr_text = TextArea(
            text=self.qr_data,
            font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
            font_size=GUIConstants.BODY_FONT_SIZE + 2,
            is_text_centered=True,
            auto_line_break=True,
            treat_chars_as_words=True,
            allow_text_overflow=True,
            screen_y=3 * GUIConstants.EDGE_PADDING,
            screen_x=GUIConstants.EDGE_PADDING,
            height=self.canvas_height
            - 4 * GUIConstants.EDGE_PADDING
            - GUIConstants.BUTTON_HEIGHT,
            width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
        )

        # Initialize shared components
        self.back_button = Button(
            text=_("Back"),
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=self.buttons_y,
            height=GUIConstants.BUTTON_HEIGHT,
            width=self.back_button_width,
            is_selected=False,
        )

        # QR code button
        self.toggle_button = Button(
            text="QR Code",
            screen_x=self.canvas_width
            - self.toggle_button_width
            - GUIConstants.EDGE_PADDING,
            screen_y=self.buttons_y,
            width=self.toggle_button_width,
            height=GUIConstants.BUTTON_HEIGHT,
            is_selected=False,
        )

        self.components = [self.back_button, self.toggle_button, self.qr_text]
        self.selected_button = 1
        self.components[self.selected_button].is_selected = True

    def _render(self):
        """Render the screen"""
        super()._render()
        for component in self.components:
            component.render()
        self.renderer.show_image()

    def _run(self):
        self._render()
        while True:
            user_input = self.hw_inputs.wait_for(
                [
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT,
                ]
                + HardwareButtonsConstants.KEYS__ANYCLICK
            )

            if user_input == HardwareButtonsConstants.KEY_LEFT:
                if self.selected_button == 1:
                    self.components[self.selected_button].is_selected = False
                    self.selected_button = 0
                    self.components[self.selected_button].is_selected = True
                    self._render()

            elif user_input == HardwareButtonsConstants.KEY_RIGHT:
                if self.selected_button == 0:
                    self.components[self.selected_button].is_selected = False
                    self.selected_button = 1
                    self.components[self.selected_button].is_selected = True
                    self._render()

            elif user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                if self.selected_button == 0:
                    return RET_CODE__BACK_BUTTON
                elif self.selected_button == 1:
                    return "SWITCH"


@dataclass
class SeedGenerateAddressScreen(BaseTopNavScreen):
    def __post_init__(self):

        self.show_back_button = False

        super().__post_init__()

        #
        self.title_text = "Introduce Address Index"

        # Track the selected address type (default to Cashaddr)
        self.address_type = "cashaddr"

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
            text="Cashaddr",
            is_text_centered=False,
            font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 4,
            width=self.right_panel_buttons_width,
            screen_x=hw_button_x,
            screen_y=hw_button_y
            - 3 * GUIConstants.COMPONENT_PADDING
            - GUIConstants.BUTTON_HEIGHT,
            is_scrollable_text=False,
            is_selected=True,  # Cashaddr is selected by default
        )

        self.hw_button2 = Button(
            text="Legacy",
            is_text_centered=False,
            font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 4,
            width=self.right_panel_buttons_width,
            screen_x=hw_button_x,
            screen_y=hw_button_y,
            is_scrollable_text=False,
        )

        self.hw_button3 = IconButton(
            icon_name=SeedCashIconsConstants.CHECK,
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
            icon_name=SeedCashIconsConstants.BACK,
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
        self.hw_button1.is_selected = self.address_type == "cashaddr"
        self.hw_button2.is_selected = self.address_type == "legacy"

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
                    # Cashaddr button pressed
                    self.address_type = "cashaddr"
                    self._render()
                    continue

                elif input == HardwareButtonsConstants.KEY2:
                    # Legacy button pressed
                    self.address_type = "legacy"
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
