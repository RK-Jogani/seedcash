import math
import logging
import time

from dataclasses import dataclass, field
from gettext import gettext as _
from PIL import Image, ImageDraw, ImageColor
from typing import Any, List, Tuple

from seedsigner.helpers.l10n import mark_for_translation as _mft
from seedsigner.gui.components import (GUIConstants,
    BaseComponent, Button, Icon, IconButton, LargeIconButton,
    SeedSignerIconConstants, TopNav, TextArea, load_image)
from seedsigner.gui.keyboard import Keyboard, TextEntryDisplay
from seedsigner.hardware.buttons import HardwareButtonsConstants, HardwareButtons
from seedsigner.models.encode_qr import BaseQrEncoder
from seedsigner.models.settings import SettingsConstants
from seedsigner.models.threads import BaseThread, ThreadsafeCounter

logger = logging.getLogger(__name__)


# Must be huge numbers to avoid conflicting with the selected_button returned by the
#   screens with buttons.
RET_CODE__BACK_BUTTON = 1000
RET_CODE__POWER_BUTTON = 1001



@dataclass
class BaseScreen(BaseComponent):
    def __post_init__(self):
        super().__post_init__()
        
        self.hw_inputs = HardwareButtons.get_instance()

        # Implementation classes can add their own BaseThread to run in parallel with the
        # main execution thread.
        self.threads: List[BaseThread] = []

        # Implementation classes can add additional BaseComponent-derived objects to the
        # list. They'll be called to `render()` themselves in BaseScreen._render().
        self.components: List[BaseComponent] = []

        # Implementation classes can add PIL.Image objs here. Format is a tuple of the
        # Image and its (x,y) paste coords.
        self.paste_images: List[Tuple] = []

        # Tracks position on scrollable pages, determines which elements are visible.
        self.scroll_y = 0
    

    def get_threads(self) -> List[BaseThread]:
        threads = self.threads.copy()
        for component in self.components:
            threads += component.threads
        return threads


    def display(self) -> Any:
        try:
            with self.renderer.lock:
                self._render()
                self.renderer.show_image()

            for t in self.get_threads():
                if not t.is_alive():
                    t.start()

            return self._run()
        except Exception as e:
            repr(e)
            raise e
        finally:
            for t in self.get_threads():
                t.stop()

            for t in self.get_threads():
                # Wait for each thread to stop; equivalent to `join()` but gracefully
                # handles threads that were never run (necessary for screenshot generator
                # compatibility, perhaps other edge cases).
                while t.is_alive():
                    time.sleep(0.01)


    def clear_screen(self):
        # Clear the whole canvas
        self.image_draw.rectangle(
            (0, 0, self.canvas_width, self.canvas_height),
            fill=0,
        )


    def _render(self):
        self.clear_screen()

        # TODO: Check self.scroll_y and only render visible elements
        for component in self.components:
            component.render()

        for img, coords in self.paste_images:
            self.canvas.paste(img, coords)


    def _run_callback(self):
        """
            Optional implementation step that's called during each _run() loop.

            Loop will continue if it returns None.
            If it returns a value, the Screen will exit and relay that return value to
            its parent View.
        """
        pass


    def _run(self):
        """
            Screen can run on its own until it returns a final exit input from the user.

            For example: A basic menu screen where the user can key up and down. The
            Screen can handle the UI updates to light up the currently selected menu item
            on its own. Only when the user clicks to make a selection would _run() exit
            and return the selected option.

            In general, _run() will be implemented as a continuous loop waiting for user
            input and redrawing the screen as needed. When it redraws, it must claim
            the `Renderer.lock` to ensure that its updates don't conflict with any other
            threads that might be updating the screen at the same time (e.g. flashing
            warning edges, auto-scrolling long titles or buttons, etc).

            Just note that this loop cannot hold the lock indefinitely! Each iteration
            through the loop should claim the lock, render, and then release it.
        """
        raise Exception("Must implement in a child class")



class LoadingScreenThread(BaseThread):
    def __init__(self, text: str = None):
        super().__init__()
        self.text =text


    def run(self):
        from seedsigner.gui.renderer import Renderer
        renderer: Renderer = Renderer.get_instance()

        center_image = load_image("btc_logo_60x60.png")
        orbit_gap = 2*GUIConstants.COMPONENT_PADDING
        bounding_box = (
            int((renderer.canvas_width - center_image.width)/2 - orbit_gap),
            int((renderer.canvas_height - center_image.height)/2 - orbit_gap),
            int((renderer.canvas_width + center_image.width)/2 + orbit_gap),
            int((renderer.canvas_height + center_image.height)/2 + orbit_gap),
        )
        position = 0
        arc_sweep = 45
        arc_color = "#ff9416"
        arc_trailing_color = "#80490b"

        # Need to flush the screen
        with renderer.lock:
            renderer.draw.rectangle((0, 0, renderer.canvas_width, renderer.canvas_height), fill=GUIConstants.BACKGROUND_COLOR)
            renderer.canvas.paste(center_image, (bounding_box[0] + orbit_gap, bounding_box[1] + orbit_gap))

            if self.text:
                TextArea(
                    text=self.text,
                    font_size=GUIConstants.get_top_nav_title_font_size(),
                    screen_y=int((renderer.canvas_height - bounding_box[3])/2),
                ).render()

        while self.keep_running:
            with renderer.lock:
                # Render leading arc
                renderer.draw.arc(
                    bounding_box,
                    start=position,
                    end=position + arc_sweep,
                    fill=arc_color,
                    width=GUIConstants.COMPONENT_PADDING
                )

                # Render trailing arc
                renderer.draw.arc(
                    bounding_box,
                    start=position - arc_sweep,
                    end=position,
                    fill=arc_trailing_color,
                    width=GUIConstants.COMPONENT_PADDING
                )

                # Erase previous trailing arc leading arc
                renderer.draw.arc(
                    bounding_box,
                    start=position - 2*arc_sweep,
                    end=position - arc_sweep,
                    fill=GUIConstants.BACKGROUND_COLOR,
                    width=GUIConstants.COMPONENT_PADDING
                )

                renderer.show_image()
            position += arc_sweep



@dataclass
class BaseTopNavScreen(BaseScreen):
    top_nav_icon_name: str = None
    top_nav_icon_color: str = None
    title: str = "Screen Title"
    title_font_size: int = GUIConstants.get_top_nav_title_font_size()
    show_back_button: bool = True
    show_power_button: bool = False

    def __post_init__(self):
        super().__post_init__()
        self.top_nav = TopNav(
            icon_name=self.top_nav_icon_name,
            icon_color=self.top_nav_icon_color,
            text=_(self.title),  # Wrap here for just-in-time translations
            font_size=self.title_font_size,
            width=self.canvas_width,
            height=GUIConstants.TOP_NAV_HEIGHT,
            show_back_button=self.show_back_button,
            show_power_button=self.show_power_button,
        )
        self.is_input_in_top_nav = False

        self.components.append(self.top_nav)


    def _run(self):
        while True:
            if not self.top_nav.show_back_button and not self.top_nav.show_power_button:
                # There's no navigation away from this screen; nothing to do here
                time.sleep(0.1)
                continue

            user_input = self.hw_inputs.wait_for(HardwareButtonsConstants.ALL_KEYS)

            with self.renderer.lock:
                if not self.top_nav.is_selected and user_input in [
                        HardwareButtonsConstants.KEY_LEFT,
                        HardwareButtonsConstants.KEY_UP
                    ]:
                    self.top_nav.is_selected = True
                    self.top_nav.render_buttons()

                elif self.top_nav.is_selected and user_input in [
                        HardwareButtonsConstants.KEY_DOWN,
                        HardwareButtonsConstants.KEY_RIGHT
                    ]:
                    self.top_nav.is_selected = False
                    self.top_nav.render_buttons()

                elif self.top_nav.is_selected and user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                    return self.top_nav.selected_button
                
                else:
                    # Nothing to do with this input
                    continue

                # Write the screen updates
                self.renderer.show_image()



@dataclass
class ButtonOption:
    """
    Note: The babel config in setup.cfg will extract the `button_label` string for translation
    """
    button_label: str
    icon_name: str = None
    icon_color: str = None
    right_icon_name: str = None
    button_label_color: str = None
    return_data: Any = None
    active_button_label: str = None  # Changes displayed button label when button is active
    font_name: str = None  # Optional override
    font_size: int = None  # Optional override



@dataclass
class ButtonListScreen(BaseTopNavScreen):
    button_data: list[ButtonOption] = None
    selected_button: int = 0
    is_button_text_centered: bool = True
    is_bottom_list: bool = False

    # Cannot define these class attrs w/the get_*_font_*() methods because the attrs will
    # not be dynamically reinterpreted after initial class import.
    button_font_name: str = None
    button_font_size: int = None

    button_selected_color: str = GUIConstants.ACCENT_COLOR

    # Params for version of list used for Settings
    Button_cls = Button
    checked_buttons: List[int] = None

    # Enables returning w/buttons rendered at the same place; default behavior will
    # ensure the screen is at least scrolled to reveal the `selected_button`.
    scroll_y_initial_offset: int = None


    def __post_init__(self):
        if not self.button_font_name:
            self.button_font_name = GUIConstants.get_button_font_name()
        if not self.button_font_size:
            self.button_font_size = GUIConstants.get_button_font_size()
        super().__post_init__()

        button_height = GUIConstants.BUTTON_HEIGHT
        if len(self.button_data) == 1:
            button_list_height = button_height
        else:
            button_list_height = (len(self.button_data) * button_height) + (GUIConstants.LIST_ITEM_PADDING * (len(self.button_data) - 1))

        if self.is_bottom_list:
            button_list_y = self.canvas_height - (button_list_height + GUIConstants.EDGE_PADDING)
        else:
            button_list_y = self.top_nav.height + int((self.canvas_height - self.top_nav.height - button_list_height) / 2)

        self.has_scroll_arrows = False
        if button_list_y < self.top_nav.height:
            # The button list is too long; force it to run off the bottom of the screen.
            button_list_y = self.top_nav.height
            self.has_scroll_arrows = True

            # How many buttons fit on the screen before we need to start scrolling?
            num_buttons_pre_scroll = math.floor((self.canvas_height - button_list_y - GUIConstants.EDGE_PADDING) / (button_height + GUIConstants.LIST_ITEM_PADDING))

            # Force a scroll offset when necessary if none was provided
            if self.selected_button + 1 > num_buttons_pre_scroll and not self.scroll_y_initial_offset:
                # Scroll far enough to expose the selected button; +1 to account for the
                # height of the target button itself!
                self.scroll_y_initial_offset = (button_height + GUIConstants.LIST_ITEM_PADDING) * (self.selected_button - num_buttons_pre_scroll + 1)

        self.buttons: List[Button] = []
        for i, button_option in enumerate(self.button_data):
            if type(button_option) != ButtonOption:
                raise Exception("Refactor to ButtonOption approach needed!")

            # TODO: Refactor `Button` to optionally use ButtonOption directly?
            button_kwargs = dict(
                text=_(button_option.button_label),  # Wrap here for just-in-time translations
                active_text=_(button_option.active_button_label),  # Wrap here for just-in-time translations
                icon_name=button_option.icon_name,
                icon_color=button_option.icon_color if button_option.icon_color else GUIConstants.BUTTON_FONT_COLOR,
                is_icon_inline=True,
                right_icon_name=button_option.right_icon_name,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=button_list_y + i * (button_height + GUIConstants.LIST_ITEM_PADDING),
                scroll_y=self.scroll_y_initial_offset if self.scroll_y_initial_offset is not None else 0,
                width=self.canvas_width - (2 * GUIConstants.EDGE_PADDING),
                height=button_height,
                is_text_centered=self.is_button_text_centered,
                font_name=button_option.font_name if button_option.font_name else self.button_font_name,
                font_size=button_option.font_size if button_option.font_size else self.button_font_size,
                font_color=button_option.button_label_color if button_option.button_label_color else GUIConstants.BUTTON_FONT_COLOR,
                selected_color=self.button_selected_color,
                is_scrollable_text=True,  # We need to use the ScrollableText class for long button labels
            )
            if self.checked_buttons and i in self.checked_buttons:
                button_kwargs["is_checked"] = True
            button = self.Button_cls(**button_kwargs)
            self.buttons.append(button)

        if self.has_scroll_arrows:
            self.arrow_half_width = 10
            self.cur_scroll_y = self.scroll_y_initial_offset if self.scroll_y_initial_offset is not None else 0
            self.up_arrow_img = Image.new("RGBA", size=(2 * self.arrow_half_width, 8), color="black")
            self.up_arrow_img_y = self.top_nav.height - 12
            arrow_draw = ImageDraw.Draw(self.up_arrow_img)
            arrow_draw.line((self.arrow_half_width, 1, 0, 7), fill=GUIConstants.BUTTON_FONT_COLOR)
            arrow_draw.line((self.arrow_half_width, 1, 2 * self.arrow_half_width, 7), fill=GUIConstants.BUTTON_FONT_COLOR)

            self.down_arrow_img = Image.new("RGBA", size=(2 * self.arrow_half_width, 8), color="black")
            self.down_arrow_img_y = self.canvas_height - 16 + 2
            arrow_draw = ImageDraw.Draw(self.down_arrow_img)
            center_x = int(self.canvas_width / 2)
            arrow_draw.line((self.arrow_half_width, 7, 0, 1), fill=GUIConstants.BUTTON_FONT_COLOR)
            arrow_draw.line((self.arrow_half_width, 7, 2 * self.arrow_half_width, 1), fill=GUIConstants.BUTTON_FONT_COLOR)

        cur_selected_button = self.buttons[self.selected_button]
        cur_selected_button.is_selected = True


    def get_threads(self) -> List[BaseThread]:
        threads = super().get_threads()
        for button in self.buttons:
            if button.is_scrollable_text:
                threads += button.threads
        return threads


    def _render(self):
        super()._render()
        self._render_visible_buttons()

        # Write the screen updates
        self.renderer.show_image()


    def _render_visible_buttons(self):
        if self.has_scroll_arrows:
            self._render_up_arrow()
            self._render_down_arrow()

        for i, button in enumerate(self.buttons):
            if not self.has_scroll_arrows:
                button.render()
                continue

            button_position_y = button.screen_y - button.scroll_y
            if button_position_y >= self.top_nav.height and button_position_y < self.down_arrow_img_y:
                if i == 0:
                    # We rendered the top button; no more to scroll up for.
                    self._hide_up_arrow()

                if i == len(self.buttons) - 1:
                    # We just pulled up the last button; no more to scroll down for.
                    self._hide_down_arrow()

                # Render the button after the arrows to cover up overlap
                button.render()


    def _render_up_arrow(self):
        self.canvas.paste(self.up_arrow_img, (int(self.canvas_width / 2) - self.arrow_half_width, self.up_arrow_img_y))

    def _render_down_arrow(self):
        self.canvas.paste(self.down_arrow_img, (int(self.canvas_width / 2) - self.arrow_half_width, self.down_arrow_img_y))

    def _hide_up_arrow(self):
        self.image_draw.rectangle(
            (
                int(self.canvas_width / 2) - self.arrow_half_width, self.up_arrow_img_y,
                int(self.canvas_width / 2) + self.arrow_half_width, self.up_arrow_img_y + self.up_arrow_img.height
            ),
            fill="black"
        )

    def _hide_down_arrow(self):
        self.image_draw.rectangle(
            (
                int(self.canvas_width / 2) - self.arrow_half_width, self.down_arrow_img_y,
                int(self.canvas_width / 2) + self.arrow_half_width, self.down_arrow_img_y + self.down_arrow_img.height
            ),
            fill="black"
        )


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
                ] + HardwareButtonsConstants.KEYS__ANYCLICK
            )

            with self.renderer.lock:
                if not self.top_nav.is_selected and (
                        user_input == HardwareButtonsConstants.KEY_LEFT or (
                            user_input == HardwareButtonsConstants.KEY_UP and self.selected_button == 0
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
                        next_selected_button: Button = self.buttons[self.selected_button]
                        cur_selected_button.is_selected = False
                        next_selected_button.is_selected = True
                        if self.has_scroll_arrows and next_selected_button.screen_y - next_selected_button.scroll_y + next_selected_button.height < self.top_nav.height:
                            # Selected a Button that's off the top of the screen
                            frame_scroll = cur_selected_button.screen_y - next_selected_button.screen_y
                            for button in self.buttons:
                                button.scroll_y -= frame_scroll
                            self._render_visible_buttons()
                        else:
                            cur_selected_button.render()
                            next_selected_button.render()

                elif user_input == HardwareButtonsConstants.KEY_DOWN or (
                        self.top_nav.is_selected and user_input == HardwareButtonsConstants.KEY_RIGHT
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
                        next_selected_button: Button = self.buttons[self.selected_button]
                        cur_selected_button.is_selected = False
                        next_selected_button.is_selected = True

                    if self.has_scroll_arrows and (
                            next_selected_button.screen_y - next_selected_button.scroll_y + next_selected_button.height > self.down_arrow_img_y
                        ):
                        # Selected a Button that's off the bottom of the screen
                        frame_scroll = next_selected_button.screen_y - cur_selected_button.screen_y
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
class LargeButtonScreen(BaseScreen):
    button_data: list = None
    button_font_name: str = None
    button_font_size: int = None
    button_selected_color: str = GUIConstants.ACCENT_COLOR
    selected_button: int = 0

    def __post_init__(self):
        if not self.button_font_name:
            self.button_font_name = GUIConstants.get_button_font_name()
        if not self.button_font_size:
            self.button_font_size = GUIConstants.get_button_font_size() + 2

        super().__post_init__()

        if not self.button_data:
            raise Exception("button_data must be provided")

        # Calculate available height for main buttons (excluding bottom power button)
        num_main_buttons = len(self.button_data)
        total_padding = (num_main_buttons - 1) * GUIConstants.COMPONENT_PADDING
        max_button_height = (self.canvas_height - total_padding - 2 * GUIConstants.EDGE_PADDING - GUIConstants.TOP_NAV_BUTTON_SIZE) // num_main_buttons
        button_size = min(self.canvas_width - 2 * GUIConstants.EDGE_PADDING, max_button_height)

        # Center the column of buttons
        total_buttons_height = num_main_buttons * button_size + total_padding
        button_start_y = (self.canvas_height - GUIConstants.TOP_NAV_BUTTON_SIZE - GUIConstants.EDGE_PADDING - total_buttons_height) // 2
        button_start_x = (self.canvas_width - button_size) // 2

        self.buttons = []
        for i, button_option in enumerate(self.button_data):
            # Support both ButtonOption and dict for button_data
            if isinstance(button_option, ButtonOption):
                button_label = button_option.button_label
                icon_name = button_option.icon_name
            elif isinstance(button_option, dict):
                button_label = button_option.get("button_label", "")
                icon_name = button_option.get("icon_name", None)
            else:
                raise Exception("button_data must be ButtonOption or dict")

            button_args = {
                "text": _(button_label),
                "screen_x": button_start_x,
                "screen_y": button_start_y,
                "width": button_size,
                "height": button_size,
                "is_text_centered": True,
                "font_name": self.button_font_name,
                "font_size": self.button_font_size,
                "selected_color": self.button_selected_color,
            }
            if icon_name:
                button_args["icon_name"] = icon_name
                button_args["text_y_offset"] = int(48 / 240 * self.renderer.canvas_height) + GUIConstants.COMPONENT_PADDING
                button = LargeIconButton(**button_args)
            else:
                button = Button(**button_args)

            self.buttons.append(button)
            self.components.append(button)

            button_start_y += button_size + GUIConstants.COMPONENT_PADDING

        # Add the small power button at the bottom right as a selectable button
        self.bottom_button = IconButton(
            icon_name=SeedSignerIconConstants.POWER,
            icon_size=GUIConstants.ICON_INLINE_FONT_SIZE,
            screen_x=self.canvas_width - GUIConstants.TOP_NAV_BUTTON_SIZE - GUIConstants.EDGE_PADDING,
            screen_y=self.canvas_height - GUIConstants.TOP_NAV_BUTTON_SIZE - GUIConstants.EDGE_PADDING,
            width=GUIConstants.TOP_NAV_BUTTON_SIZE,
            height=GUIConstants.TOP_NAV_BUTTON_SIZE,
        )
        self.buttons.append(self.bottom_button)  # Now selectable
        self.components.append(self.bottom_button)

        self.buttons[self.selected_button].is_selected = True

    def _run(self):
        def swap_selected_button(new_selected_button: int):
            self.buttons[self.selected_button].is_selected = False
            self.buttons[self.selected_button].render()
            self.selected_button = new_selected_button
            self.buttons[self.selected_button].is_selected = True
            self.buttons[self.selected_button].render()

        while True:
            ret = self._run_callback()
            if ret is not None:
                return ret

            user_input = self.hw_inputs.wait_for(
                [
                    HardwareButtonsConstants.KEY_UP,
                    HardwareButtonsConstants.KEY_DOWN,
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT
                ] + HardwareButtonsConstants.KEYS__ANYCLICK
            )

            with self.renderer.lock:
                if user_input == HardwareButtonsConstants.KEY_UP:
                    # Navigation wraps through all buttons, including the power button at the bottom.
                    if self.selected_button == 0:
                        pass  # Already at top button
                    else:
                        swap_selected_button(self.selected_button - 1)

                elif user_input == HardwareButtonsConstants.KEY_DOWN:
                    # After the last main button, next down selects the power button.
                    if self.selected_button < len(self.buttons) - 1:
                        swap_selected_button(self.selected_button + 1)

                elif user_input in HardwareButtonsConstants.KEYS__ANYCLICK:
                    return self.selected_button

                self.renderer.show_image()

                self.renderer.show_image()


@dataclass
class QRDisplayScreen(BaseScreen):
    qr_encoder: BaseQrEncoder = None

    class QRDisplayThread(BaseThread):
        def __init__(self, qr_encoder: BaseQrEncoder, qr_brightness: ThreadsafeCounter, tips_start_time: ThreadsafeCounter):
            from seedsigner.gui.renderer import Renderer
            super().__init__()
            self.qr_encoder = qr_encoder
            self.qr_brightness = qr_brightness
            self.renderer = Renderer.get_instance()
            self.tips_start_time = tips_start_time


        def render_brightness_tip(self, image: Image.Image) -> None:
            # TODO: Refactor ToastOverlay to support two lines of icon + text and use
            # that instead of this more manual approach.

            # Instantiate a temp Image and ImageDraw object to draw on
            rectangle_width = image.width
            rectangle_height = GUIConstants.COMPONENT_PADDING * 2 + GUIConstants.get_body_font_size() * 2 + GUIConstants.BODY_LINE_SPACING
            rectangle = Image.new('RGBA', (rectangle_width, rectangle_height), (0, 0, 0, 0))
            img_draw = ImageDraw.Draw(rectangle)

            overlay_opacity = 224

            # Create a semi-transparent background for the overlay, rounded edges, w/a 1-pixel gap from the edges
            img_draw.rounded_rectangle((1, 0, rectangle_width - 2, rectangle_height - 1), radius=8, fill=(0, 0, 0, overlay_opacity))

            chevron_up_icon = Icon(
                image_draw=img_draw,
                canvas=rectangle,
                screen_x=GUIConstants.EDGE_PADDING*2 + 1,
                screen_y=GUIConstants.COMPONENT_PADDING + 4,  # +4 fudge factor to account for where the chevron is drawn relative to baseline
                icon_name=SeedSignerIconConstants.CHEVRON_UP,
                icon_size=GUIConstants.get_body_font_size(),
            )
            chevron_up_icon.render()

            chevron_down_icon = Icon(
                image_draw=img_draw,
                canvas=rectangle,
                screen_x=chevron_up_icon.screen_x,
                screen_y=chevron_up_icon.screen_y + chevron_up_icon.icon_size + GUIConstants.BODY_LINE_SPACING,
                icon_name=SeedSignerIconConstants.CHEVRON_DOWN,
                icon_size=chevron_up_icon.icon_size,
            )
            chevron_down_icon.render()

            # TRANSLATOR_NOTE: Increase QR code screen brightness
            text = _("Brighter")
            TextArea(
                image_draw=img_draw,
                canvas=rectangle,
                text=text,
                font_size=GUIConstants.get_body_font_size(),
                font_name=GUIConstants.get_button_font_name(),
                background_color=(0, 0, 0, overlay_opacity),
                edge_padding=0,
                is_text_centered=False,
                auto_line_break=False,
                width=int(rectangle_width/2),
                screen_x=chevron_up_icon.screen_x + GUIConstants.ICON_INLINE_FONT_SIZE,
                screen_y=chevron_up_icon.screen_y - 2,  # -2 to account for Icon's positioning
                allow_text_overflow=False
            ).render()

            # TRANSLATOR_NOTE: Decrease QR code screen brightness
            text = _("Darker")
            TextArea(
                image_draw=img_draw,
                canvas=rectangle,
                text=text,
                font_size=GUIConstants.get_body_font_size(),
                font_name=GUIConstants.get_button_font_name(),
                background_color=(0, 0, 0, overlay_opacity),
                edge_padding=0,
                is_text_centered=False,
                auto_line_break=False,
                width=int(rectangle_width/2),
                screen_x=chevron_down_icon.screen_x + GUIConstants.ICON_INLINE_FONT_SIZE,
                screen_y=chevron_down_icon.screen_y - 2,  # -2 to account for Icon's positioning
                allow_text_overflow=False
            ).render()

            # Write our temp Image onto the main image
            image.paste(rectangle, (0, image.height - rectangle_height - 1), rectangle)


        def run(self):
            from seedsigner.models.settings import Settings
            settings = Settings.get_instance()
            cur_brightness_setting = settings.get_value(SettingsConstants.SETTING__QR_BRIGHTNESS_TIPS)
            is_brightness_tip_enabled = cur_brightness_setting == SettingsConstants.OPTION__ENABLED
            pending_encoder_restart = False

            # Loop whether the QR is a single frame or animated; each loop might adjust
            # brightness setting.
            while self.keep_running:
                # convert the self.qr_brightness integer (31-255) into hex triplets
                hex_color = (hex(self.qr_brightness.cur_count).split('x')[1]) * 3

                # Display the brightness tips toast
                duration = 10 ** 9 * 1.2  # 1.2 seconds
                if is_brightness_tip_enabled and time.time_ns() - self.tips_start_time.cur_count < duration:
                    image = self.qr_encoder.part_to_image(self.qr_encoder.cur_part(), 240, 240, border=2, background_color=hex_color)
                    self.render_brightness_tip(image)
                    pending_encoder_restart = True
                else:
                    # Only advance the QR animation when the brightness tip is not displayed
                    if pending_encoder_restart:
                        # Animated QRs should restart their frame sequence after the
                        # brightness tip is stowed.
                        self.qr_encoder.restart()
                        pending_encoder_restart = False
                    image = self.qr_encoder.next_part_image(240, 240, border=2, background_color=hex_color)

                with self.renderer.lock:
                    self.renderer.show_image(image)

                # Target n held frames per second before rendering next QR image
                time.sleep(5 / 30.0)


    def __post_init__(self):
        from seedsigner.models.settings import Settings
        super().__post_init__()

        # Shared coordination var so the display thread can detect success
        settings = Settings.get_instance()
        self.qr_brightness = ThreadsafeCounter(
            initial_value=settings.get_value(SettingsConstants.SETTING__QR_BRIGHTNESS))
        self.tips_start_time = ThreadsafeCounter(initial_value=time.time_ns())

        self.threads.append(QRDisplayScreen.QRDisplayThread(
            qr_encoder=self.qr_encoder,
            qr_brightness=self.qr_brightness,
            tips_start_time=self.tips_start_time
        ))


    def _run(self):
        from seedsigner.models.settings import Settings

        while True:
            user_input = self.hw_inputs.wait_for(
                [
                    HardwareButtonsConstants.KEY_UP,
                    HardwareButtonsConstants.KEY_DOWN,
                    HardwareButtonsConstants.KEY_LEFT,
                    HardwareButtonsConstants.KEY_RIGHT,
                ] + HardwareButtonsConstants.KEYS__ANYCLICK
            )
            if user_input == HardwareButtonsConstants.KEY_DOWN:
                # Reduce QR code background brightness
                self.qr_brightness.set_value(max(31, self.qr_brightness.cur_count - 31))
                self.tips_start_time.set_value(time.time_ns())

            elif user_input == HardwareButtonsConstants.KEY_UP:
                # Incrase QR code background brightness
                self.qr_brightness.set_value(min(self.qr_brightness.cur_count + 31, 255))
                self.tips_start_time.set_value(time.time_ns())

            else:
                # Any other input exits the screen
                self.threads[-1].stop()
                while self.threads[-1].is_alive():
                    time.sleep(0.01)
                break

        Settings.get_instance().set_value(SettingsConstants.SETTING__QR_BRIGHTNESS, self.qr_brightness.cur_count)



@dataclass
class LargeIconStatusScreen(ButtonListScreen):
    title: str = _mft("Success!")
    status_icon_name: str = SeedSignerIconConstants.SUCCESS
    status_icon_size: int = GUIConstants.ICON_PRIMARY_SCREEN_SIZE
    status_color: str = GUIConstants.SUCCESS_COLOR
    status_headline: str = None
    text: str = ""                          # The body text of the screen
    text_edge_padding: int = GUIConstants.EDGE_PADDING
    button_data: list = None
    allow_text_overflow: bool = False


    def __post_init__(self):
        if not self.button_data:
            self.button_data = [ButtonOption("OK")]
        self.is_bottom_list = True
        super().__post_init__()

        self.status_icon = Icon(
            icon_name=self.status_icon_name,
            icon_size=self.status_icon_size,
            icon_color=self.status_color,
        )
        self.status_icon.screen_y = self.top_nav.height - int(GUIConstants.COMPONENT_PADDING/2)
        self.status_icon.screen_x = int((self.canvas_width - self.status_icon.width) / 2)
        self.components.append(self.status_icon)

        next_y = self.status_icon.screen_y + self.status_icon.height + int(GUIConstants.COMPONENT_PADDING/2)
        if self.status_headline:
            self.warning_headline_textarea = TextArea(
                text=_(self.status_headline),  # Wrap here for just-in-time translations
                width=self.canvas_width,
                screen_y=next_y,
                font_color=self.status_color,
                auto_line_break=False,  # Force headline to be on one line
            )
            self.components.append(self.warning_headline_textarea)
            next_y = next_y + self.warning_headline_textarea.height

        if self.text:
            self.components.append(TextArea(
                height=self.buttons[0].screen_y - next_y,
                text=_(self.text),
                width=self.canvas_width,
                edge_padding=self.text_edge_padding,  # Don't render all the way up to the far left/right edges
                screen_y=next_y,
            ))



class WarningEdgesThread(BaseThread):
    def __init__(self, args):
        super().__init__()
        self.args = args


    def run(self):
        screen = self.args[0]
        inhale_step = 1
        inhale_max = 10
        inhale_hold = 8
        cur_inhale_hold = 0
        inhale_factor = 0
        rgb = ImageColor.getrgb(screen.status_color)

        def render_border(color, width):
            screen.image_draw.rectangle(
                (0, 0, screen.canvas_width, screen.canvas_height),
                fill=None,
                outline=color,
                width=width,
                # radius=5
            )

        try:
            while self.keep_running:
                with screen.renderer.lock:
                    # Ramp the edges from a darker version out to full color
                    inhale_scalar = inhale_factor * int(255/inhale_max)
                    for index, n in enumerate(range(4, -1, -1)):
                        # Reverse range steadily increases rgb in brightness until reaching full.
                        # 34 == 0x22; just eyeballed a good step size

                        r = max(0, rgb[0] - 34*n - inhale_scalar)
                        g = max(0, rgb[1] - 34*n - inhale_scalar)
                        b = max(0, rgb[2] - 34*n - inhale_scalar)

                        # `index` shrinks the border at each step
                        render_border((r, g, b), GUIConstants.EDGE_PADDING - 2 - index)

                    # Write the screen updates
                    screen.renderer.show_image()
                
                if inhale_factor == inhale_max:
                    inhale_step = -1
                elif inhale_factor == 0 and inhale_step == -1:
                    cur_inhale_hold += 1
                    if cur_inhale_hold > inhale_hold:
                        inhale_step = 1
                        cur_inhale_hold = 0
                    else:
                        # It's about to be decremented below zero
                        inhale_factor = 1
                inhale_factor += inhale_step

                # Target ~10fps
                time.sleep(0.05)

        except KeyboardInterrupt as e:
            self.stop()
            raise e



@dataclass
class WarningEdgesMixin:
    status_color: str = GUIConstants.WARNING_COLOR
    text_edge_padding: int = 2 * GUIConstants.EDGE_PADDING

    def __post_init__(self):
        super().__post_init__()

        self.threads.append(WarningEdgesThread(args=(self,)))



@dataclass
class WarningScreen(WarningEdgesMixin, LargeIconStatusScreen):
    """
    Exclamation point icon + yellow WARNING color
    """
    title: str = _mft("Caution")
    status_icon_name: str = SeedSignerIconConstants.WARNING
    status_color: str = GUIConstants.WARNING_COLOR
    status_headline: str = _mft("Privacy Leak!")     # The colored text under the alert icon
    button_data: list = field(default_factory=lambda: [ButtonOption("I Understand")])



@dataclass
class DireWarningScreen(WarningScreen):
    """
    Exclamation point icon + orange DIRE_WARNING color
    """
    status_headline: str = _mft("Classified Info!")     # The colored text under the alert icon
    status_color: str = GUIConstants.DIRE_WARNING_COLOR



@dataclass
class ErrorScreen(WarningScreen):
    """
    X icon + red ERROR color
    """
    title: str = _mft("Error")
    status_icon_name: str = SeedSignerIconConstants.ERROR
    status_color: str = GUIConstants.ERROR_COLOR



@dataclass
class ResetScreen(BaseTopNavScreen):
    def __post_init__(self):
        self.title = _("Restarting")
        self.show_back_button = False
        super().__post_init__()

        self.components.append(TextArea(
            text=_("SeedSigner is restarting.\n\nAll in-memory data will be wiped."),
            screen_y=self.top_nav.height,
            height=self.canvas_height - self.top_nav.height,
        ))



@dataclass
class PowerOffScreen(BaseTopNavScreen):
    def __post_init__(self):
        self.title = _("Powering Off")
        self.show_back_button = False
        super().__post_init__()

        self.components.append(TextArea(
            text=_("Please wait about 30 seconds before disconnecting power."),
            screen_y=self.top_nav.height,
            height=self.canvas_height - self.top_nav.height,
        ))



@dataclass
class PowerOffNotRequiredScreen(BaseTopNavScreen):
    def __post_init__(self):
        self.title = _("Just Unplug It")
        self.show_back_button = True
        super().__post_init__()

        self.components.append(TextArea(
            text=_("It is safe to disconnect power at any time."),
            screen_y=self.top_nav.height,
            height=self.canvas_height - self.top_nav.height,
        ))



@dataclass
class KeyboardScreen(BaseTopNavScreen):
    """
        Generalized Screen for a single Keyboard layout writing user input to a
        TextEntryDisplay.
        
        Args:
        * rows
        * cols
        * keyboard_font_name
        * keyboard_font_size: Specify `None` to auto-size to Key height.
        * key_height: Specify `None` to maximize key height to available space.
        * keys_charset: Specify the chars displayed on the keys of the keyboard.
        * keys_to_values: Optional mapping from key_charset to input value (e.g. dice icon to digit).
        * return_after_n_chars: exits and returns the user's input after n characters.
        * show_save_button: Render a KEY3 soft button for save & exit
        * initial_value: initialize the TextEntryDisplay with an existing string
    """
    rows: int = None
    cols: int = None
    keyboard_font_name: str = GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME
    keyboard_font_size: int = None
    key_height: int = None
    keys_charset: str = None
    keys_to_values: dict = None
    return_after_n_chars: int = None
    show_save_button: bool = False
    initial_value: str = ""

    def __post_init__(self):
        if self.keyboard_font_size is None:
            self.keyboard_font_size = GUIConstants.get_top_nav_title_font_size() + 2

        super().__post_init__()

        if self.initial_value:
            self.user_input = self.initial_value
        else:
            self.user_input = ""

        # Set up the keyboard params        
        if self.show_save_button:
            right_panel_buttons_width = 60
            hw_button_x = self.canvas_width - right_panel_buttons_width + GUIConstants.COMPONENT_PADDING
            hw_button_y = int(self.canvas_height - GUIConstants.BUTTON_HEIGHT) / 2 + 60
            
            self.keyboard_width = self.canvas_width - (GUIConstants.EDGE_PADDING + GUIConstants.COMPONENT_PADDING + right_panel_buttons_width - GUIConstants.COMPONENT_PADDING)

            # Render the right button panel (only has a Key3 "Save" button)
            self.save_button = IconButton(
                icon_name=SeedSignerIconConstants.CHECK,
                icon_color=GUIConstants.SUCCESS_COLOR,
                width=right_panel_buttons_width,
                screen_x=hw_button_x,
                screen_y=hw_button_y,
            )
            self.components.append(self.save_button)
        else:
            self.keyboard_width = self.canvas_width - 2*GUIConstants.EDGE_PADDING

        text_entry_display_y = self.top_nav.height
        text_entry_display_height = 30

        keyboard_start_y = text_entry_display_y + text_entry_display_height + GUIConstants.COMPONENT_PADDING
        if self.key_height is None:
            self.key_height = int((self.canvas_height - GUIConstants.EDGE_PADDING - text_entry_display_y - text_entry_display_height - GUIConstants.COMPONENT_PADDING - (self.rows - 1) * 2) / self.rows)

        if self.keyboard_font_size:
            font_size = self.keyboard_font_size
        else:
            # Scale with button height
            font_size = self.key_height - GUIConstants.COMPONENT_PADDING

        self.keyboard = Keyboard(
            draw=self.renderer.draw,
            charset=self.keys_charset,
            font_name=self.keyboard_font_name,
            font_size=font_size,
            rows=self.rows,
            cols=self.cols,
            rect=(
                GUIConstants.EDGE_PADDING,
                keyboard_start_y,
                GUIConstants.EDGE_PADDING + self.keyboard_width,
                keyboard_start_y + self.rows * self.key_height + (self.rows - 1) * 2
            ),
            auto_wrap=[Keyboard.WRAP_LEFT, Keyboard.WRAP_RIGHT],
            render_now=False
        )
        self.keyboard.set_selected_key(selected_letter=self.keys_charset[0])

        self.text_entry_display = TextEntryDisplay(
            canvas=self.renderer.canvas,
            rect=(
                GUIConstants.EDGE_PADDING,
                text_entry_display_y,
                self.canvas_width - GUIConstants.EDGE_PADDING,
                text_entry_display_y + text_entry_display_height
            ),
            cursor_mode=TextEntryDisplay.CURSOR_MODE__BAR,
            is_centered=False,
            cur_text=self.initial_value,
        )


    def _render(self):
        super()._render()

        self.keyboard.render_keys()
        self.text_entry_display.render()

        self.renderer.show_image()


    def _run(self):
        self.cursor_position = len(self.user_input)

        # Start the interactive update loop
        while True:
            input = self.hw_inputs.wait_for(
                HardwareButtonsConstants.KEYS__LEFT_RIGHT_UP_DOWN + [HardwareButtonsConstants.KEY_PRESS, HardwareButtonsConstants.KEY3]
            )

            with self.renderer.lock:
                # Check possible exit conditions   
                if self.top_nav.is_selected and input == HardwareButtonsConstants.KEY_PRESS:
                    return RET_CODE__BACK_BUTTON

                elif self.show_save_button and input == HardwareButtonsConstants.KEY3:
                    # Save!
                    if len(self.user_input) == 0:
                        # Don't try to submit zero input
                        continue

                    # First show the save button reacting to the click
                    self.save_button.is_selected = True
                    self.save_button.render()
                    self.renderer.show_image()

                    # Then return the input to the View
                    return self.user_input.strip()

                # Process normal input
                if input in [HardwareButtonsConstants.KEY_UP, HardwareButtonsConstants.KEY_DOWN] and self.top_nav.is_selected:
                    # We're navigating off the previous button
                    self.top_nav.is_selected = False
                    self.top_nav.render_buttons()

                    # Override the actual input w/an ENTER signal for the Keyboard
                    if input == HardwareButtonsConstants.KEY_DOWN:
                        input = Keyboard.ENTER_TOP
                    else:
                        input = Keyboard.ENTER_BOTTOM
                elif input in [HardwareButtonsConstants.KEY_LEFT, HardwareButtonsConstants.KEY_RIGHT] and self.top_nav.is_selected:
                    # ignore
                    continue

                ret_val = self.keyboard.update_from_input(input)

                # Now process the result from the keyboard
                if ret_val in Keyboard.EXIT_DIRECTIONS:
                    self.top_nav.is_selected = True
                    self.top_nav.render_buttons()

                elif ret_val in Keyboard.ADDITIONAL_KEYS and input == HardwareButtonsConstants.KEY_PRESS:
                    if ret_val == Keyboard.KEY_BACKSPACE["code"]:
                        if len(self.user_input) > 0:
                            self.user_input = self.user_input[:-1]
                            self.cursor_position -= 1

                elif input == HardwareButtonsConstants.KEY_PRESS and ret_val not in Keyboard.ADDITIONAL_KEYS:
                    # User has locked in the current letter
                    if self.keys_to_values:
                        # Map the Key display char to its output value (e.g. dice icon to digit)
                        ret_val = self.keys_to_values[ret_val]
                    self.user_input += ret_val
                    self.cursor_position += 1

                    if self.cursor_position == self.return_after_n_chars:
                        return self.user_input

                    # Render a new TextArea over the TopNav title bar
                    if self.update_title():
                        TextArea(
                            text=self.title,
                            font_name=GUIConstants.get_top_nav_title_font_name(),
                            font_size=GUIConstants.get_top_nav_title_font_size(),
                            height=self.top_nav.height,
                        ).render()
                        self.top_nav.render_buttons()

                elif input in HardwareButtonsConstants.KEYS__LEFT_RIGHT_UP_DOWN:
                    # Live joystick movement; haven't locked this new letter in yet.
                    # Leave current spot blank for now. Only update the active keyboard keys
                    # when a selection has been locked in (KEY_PRESS) or removed ("del").
                    pass

                # Render the text entry display and cursor block
                self.text_entry_display.render(self.user_input)

                self.renderer.show_image()


    def update_title(self) -> bool:
        """
            Optionally update the self.title after each completed key input.
            
            e.g. to increment the dice roll count:
                self.title = _("Roll {}".format(self.cursor_position + 1))
        """
        return False



@dataclass
class MainMenuScreen(LargeButtonScreen):
    # Override LargeButtonScreen defaults
    show_back_button: bool = False
    show_power_button: bool = True
    button_font_size: int = 16
