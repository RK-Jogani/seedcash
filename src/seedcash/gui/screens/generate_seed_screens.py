import hashlib
import logging

from dataclasses import dataclass
import time

from PIL import Image, ImageDraw


from seedcash.hardware.buttons import HardwareButtonsConstants
from seedcash.hardware.camera import Camera
from seedcash.gui.components import (
    Fonts,
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
    RET_CODE__BACK_BUTTON,
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
                label_text="fingerprint",
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

@dataclass
class ToolsImageEntropyLivePreviewScreen(BaseScreen):
    # Set how many distinct, non-blank preview frames must be collected into the preview
    # pool before the final image can be taken.
    PREVIEW_POOL_SIZE = 50

    def __post_init__(self):
        super().__post_init__()

        self.camera = Camera.get_instance()

        # If the stream is set to 320x240, we get pillarboxed frames (black bars on the
        # sides). But passing in square dims gives us an edge-to-edge image.
        # TODO: Figure out why (camera expecting frame dims of multiples other than 16?)
        max_dimension = max(self.canvas_width, self.canvas_height)
        self.camera.start_video_stream_mode(resolution=(max_dimension, max_dimension), framerate=24, format="rgb")


    def _run(self):
        # save preview image frames to use as additional entropy below
        preview_images = []
        instructions_font = Fonts.get_font(GUIConstants.BODY_FONT_NAME, GUIConstants.BUTTON_FONT_SIZE)

        # Pre-calculate how wide the frame counter display can be.
        # TRANSLATOR_NOTE: Counts frames collected so far vs the total required (e.g. 12/50)
        max_counter_text = "{}/{}".format(self.PREVIEW_POOL_SIZE, self.PREVIEW_POOL_SIZE)
        (left, top, right, bottom) = instructions_font.getbbox(max_counter_text)
        counter_text_width = right - left

        # The camera hands us its most recent frame on every loop pass, but the SAME frame
        # can arrive more than once. Store each image's sha256 hash so we can recognize
        # and skip the repeats. The set is intentionally never pruned. A frame identical
        # to any previously admitted frame can never be added a second time.
        preview_frame_hashes = set()

        # If the user continues holding the button that brought them into this flow, we
        # have to ensure that it doesn't trigger the ANYCLICK check below, otherwise the
        # final image capture would fire on its own the instant the preview pool fills.
        is_maybe_still_holding = True

        while True:
            if self.hw_inputs.check_for_low(HardwareButtonsConstants.KEY_LEFT):
                # Have to manually update last input time since we're not in a wait_for loop
                self.hw_inputs.update_last_input_time()
                self.words = []
                self.camera.stop_video_stream_mode()
                return RET_CODE__BACK_BUTTON

            frame: Image.Image = self.camera.read_video_stream(as_image=True)

            if frame is None:
                # Camera probably isn't ready yet
                time.sleep(0.01)
                continue

            with self.renderer.lock:
                # Account for the possibly different aspect ratio of the camera frame
                # vs the display; crop any excess.
                # TODO: This cropping may be unnecessary if the above TODO about the
                # camera resolution is solved.
                box = None
                if self.canvas_width != frame.width:
                    half_width_diff = int(abs(self.canvas_width - frame.width)/2)
                    box = (
                        half_width_diff,
                        0,
                        frame.width - half_width_diff,
                        frame.height
                    )
                elif self.canvas_height != frame.height:
                    half_height_diff = int(abs(self.canvas_height - frame.height)/2)
                    box = (
                        0,
                        half_height_diff,
                        frame.width,
                        frame.height - half_height_diff
                    )

                self.renderer.canvas.paste(frame.crop(box=box))

            # Decide whether this frame can be added to the preview pool.
            # Rule 1: the frame must not be a single flat color (e.g. an all-black frame
            # or an overexposed all-white one). getextrema() reports the lowest and
            # highest value found in each color channel; if the lowest equals the highest
            # in every channel, every pixel in the frame is identical and the frame is
            # rejected.
            frame_has_variation = False
            for lowest_value, highest_value in frame.getextrema():
                if lowest_value != highest_value:
                    frame_has_variation = True

            if frame_has_variation:
                # Rule 2: the frame must be one we have never counted before
                frame_hash = hashlib.sha256(frame.tobytes()).digest()
                if frame_hash not in preview_frame_hashes:
                    preview_frame_hashes.add(frame_hash)
                    if len(preview_images) == self.PREVIEW_POOL_SIZE:
                        # The preview pool is full. Dump the oldest and add the current
                        # frame.
                        preview_images.pop(0)
                    preview_images.append(frame)

            # Can only proceed to the final image when the preview pool is full
            if len(preview_images) == self.PREVIEW_POOL_SIZE:
                # If the ANYCLICK buttons are detected as being all released (none of
                # them cause check_for_low to return True), we can be sure that the user
                # isn't still holding down the initial button press that brought them
                # into this flow. It is then safe to arm the loop to trigger the final
                # image capture for whenever the *next* ANYCLICK button is pressed.
                if not self.hw_inputs.check_for_low(keys=HardwareButtonsConstants.KEYS__ANYCLICK):
                    # Confirmed that all ANYCLICK buttons are released. The next click
                    # can now trigger the final image capture.
                    is_maybe_still_holding = False

                elif not is_maybe_still_holding:
                    # We passed the above check; this is a fresh, explicit click. We can
                    # now capture the final image and exit this loop.

                    # Have to manually update last input time since we're not in a wait_for loop
                    self.hw_inputs.update_last_input_time()
                    self.camera.stop_video_stream_mode()

                    with self.renderer.lock:
                        self.renderer.draw.text(
                            xy=(
                                int(self.renderer.canvas_width/2),
                                self.renderer.canvas_height - GUIConstants.EDGE_PADDING
                            ),
                            text="Capturing image...",
                            fill=GUIConstants.ACCENT_COLOR,
                            font=instructions_font,
                            stroke_width=4,
                            stroke_fill=GUIConstants.BACKGROUND_COLOR,
                            anchor="ms"
                        )
                        self.renderer.show_image()

                    return preview_images

            # If we're still here, it's just another preview frame loop
            with self.renderer.lock:
                if len(preview_images) == self.PREVIEW_POOL_SIZE and not is_maybe_still_holding:
                    self.renderer.draw.text(
                        xy=(
                            int(self.renderer.canvas_width/2),
                            self.renderer.canvas_height - GUIConstants.EDGE_PADDING
                        ),
                        text="< " + "back" + "  |  " + "click a button",  # TODO: Render with UI elements instead of text
                        fill=GUIConstants.BODY_FONT_COLOR,
                        font=instructions_font,
                        stroke_width=4,
                        stroke_fill=GUIConstants.BACKGROUND_COLOR,
                        anchor="ms"
                    )

                else:
                    # Still collecting (or is_maybe_still_holding); report current
                    # progress on number of preview pool frames.

                    # TRANSLATOR_NOTE: Shown while the camera gathers the image frames a new seed requires
                    collecting_text = "Collecting entropy frames"
                    self.renderer.draw.text(
                        xy=(
                            int(self.renderer.canvas_width/2),
                            self.renderer.canvas_height - GUIConstants.EDGE_PADDING - GUIConstants.BUTTON_HEIGHT - GUIConstants.COMPONENT_PADDING
                        ),
                        text=collecting_text,
                        fill=GUIConstants.BODY_FONT_COLOR,
                        font=instructions_font,
                        stroke_width=4,
                        stroke_fill=GUIConstants.BACKGROUND_COLOR,
                        anchor="ms"
                    )

                    # Render the frame counter progress bar; same visual design as the
                    # animated QR scan progress bar.
                    rectangle = Image.new('RGBA', (self.renderer.canvas_width - 2*GUIConstants.EDGE_PADDING, GUIConstants.BUTTON_HEIGHT), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(rectangle)

                    # Start with a background rounded rectangle, same dims as the buttons
                    overlay_color = (0, 0, 0, 191)  # opacity ranges from 0-255
                    draw.rounded_rectangle(
                        (
                            (0, 0),
                            (rectangle.width, rectangle.height)
                        ),
                        fill=overlay_color,
                        radius=8,
                        outline=overlay_color,
                        width=2,
                    )

                    progress_bar_thickness = 4
                    progress_bar_width = rectangle.width - 2*GUIConstants.EDGE_PADDING - counter_text_width - int(GUIConstants.EDGE_PADDING/2)
                    progress_bar_xy = (
                            (GUIConstants.EDGE_PADDING, int((rectangle.height - progress_bar_thickness) / 2)),
                            (GUIConstants.EDGE_PADDING + progress_bar_width, int(rectangle.height + progress_bar_thickness) / 2)
                        )
                    draw.rounded_rectangle(
                        progress_bar_xy,
                        fill=GUIConstants.INACTIVE_COLOR,
                        radius=8
                    )

                    if len(preview_images) > 0:
                        draw.rounded_rectangle(
                            (
                                progress_bar_xy[0],
                                (GUIConstants.EDGE_PADDING + int(len(preview_images) * progress_bar_width / self.PREVIEW_POOL_SIZE), progress_bar_xy[1][1])
                            ),
                            fill=GUIConstants.GREEN_INDICATOR_COLOR,
                            radius=8
                        )

                    # TRANSLATOR_NOTE: Counts frames collected so far vs the total required (e.g. 12/50)
                    counter_text = "{}/{}".format(len(preview_images), self.PREVIEW_POOL_SIZE)

                    draw.text(
                        xy=(rectangle.width - GUIConstants.EDGE_PADDING, int(rectangle.height / 2)),
                        text=counter_text,
                        fill=GUIConstants.BODY_FONT_COLOR,
                        font=instructions_font,
                        anchor="rm",  # right-justified, middle
                    )

                    self.renderer.canvas.paste(rectangle, (GUIConstants.EDGE_PADDING, self.renderer.canvas_height - GUIConstants.EDGE_PADDING - rectangle.height), rectangle)

                self.renderer.show_image()

@dataclass
class ToolsImageEntropyFinalImageScreen(BaseScreen):
    final_image: Image.Image = None

    def _run(self):
        instructions_font = Fonts.get_font(GUIConstants.BODY_FONT_NAME, GUIConstants.BUTTON_FONT_SIZE)

        with self.renderer.lock:
            self.renderer.canvas.paste(self.final_image)

            # TRANSLATOR_NOTE: A prompt to the user to either accept or reshoot the image
            reshoot = "reshoot"

            # TRANSLATOR_NOTE: A prompt to the user to either accept or reshoot the image
            accept = "accept"
            self.renderer.draw.text(
                xy=(
                    int(self.renderer.canvas_width/2),
                    self.renderer.canvas_height - GUIConstants.EDGE_PADDING
                ),
                text=" < " + reshoot + "  |  " + accept + " > ",
                fill=GUIConstants.BODY_FONT_COLOR,
                font=instructions_font,
                stroke_width=4,
                stroke_fill=GUIConstants.BACKGROUND_COLOR,
                anchor="ms"
            )
            self.renderer.show_image()

        # The button click that triggered the final image might still be held down as this
        # screen appears. We can't let that held button auto-dismiss the final image
        # review here. Wait until every button has been released before listening for the
        # accept/reshoot decision.
        while self.hw_inputs.check_for_low(keys=[HardwareButtonsConstants.KEY_LEFT, HardwareButtonsConstants.KEY_RIGHT] + HardwareButtonsConstants.KEYS__ANYCLICK):
            time.sleep(0.01)

        # LEFT = reshoot, RIGHT / ANYCLICK = accept
        input = self.hw_inputs.wait_for([HardwareButtonsConstants.KEY_LEFT, HardwareButtonsConstants.KEY_RIGHT] + HardwareButtonsConstants.KEYS__ANYCLICK)
        if input == HardwareButtonsConstants.KEY_LEFT:
            return RET_CODE__BACK_BUTTON


