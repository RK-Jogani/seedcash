import math
from dataclasses import dataclass
from PIL import Image, ImageDraw

from seedcash.models import visual_hash as vh
from seedcash.helpers.qr import QR

from seedcash.gui.screens.screen import (
    ButtonListScreen,
    BaseScreen,
    BaseTopNavScreen,
    RET_CODE__BACK_BUTTON,
    HardwareButtonsConstants,
    TextEntryDisplay,
    Keyboard,
    IconButton,
)

from seedcash.gui.components import (
    RoundedTextArea,
    SeedCashIconsConstants,
    GUIConstants,
    IconTextLine,
    TextArea,
    Fonts,
    Button,
)

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
            label_text="fingerprint",
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
class WalletOptionsScreen(ButtonListScreen):
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
class TranscribeSeedQRWholeQRScreen(ButtonListScreen):
    qr_data: str = None

    def __post_init__(self):
        self.title = "Transcribe SeedQR"
        self.is_bottom_list = True
        super().__post_init__()

        qr_height = self.canvas_height - GUIConstants.TOP_NAV_HEIGHT - 2 * GUIConstants.COMPONENT_PADDING
        qr_width = qr_height

        qr = QR()
        qr_image = qr.qrimage(
            data=self.qr_data,
            width=qr_width,
            height=qr_height,
            border=1,
            style=QR.STYLE__GRID
        ).convert("RGBA")

        self.paste_images.append((qr_image, (int((self.canvas_width - qr_width)/2), GUIConstants.COMPONENT_PADDING)))

@dataclass
class TranscribeSeedQRZoomedInScreen(BaseScreen):
    """
    QR codes are defined by the number of "modules" (squares), e.g. 21x21 modules.

    Each module will be rendered as a square of pixels, e.g. 24x24 pixels.

    In this Screen, a "zone" will mean a square module area, e.g. 5x5 modules, that
    corresponds to the SeedQR templates which include zone guidelines and labels
    (e.g. "B-3").
    """
    qr_data: str = None
    num_modules: int = None
    initial_zone_x: int = 0
    initial_zone_y: int = 0

    def __post_init__(self):
        super().__post_init__()

        # Render an oversized QR code that we can view up close
        self.pixels_per_module = 24

        # Border must accommodate the 3 blocks outside the center 5x5 mask plus up to
        # 1 empty block inside the 5x5 mask (29x29 has a 4-block final col/row).
        self.num_qr_border_modules = 4
        if self.num_modules == 21:
            # Optimize for 21x21
            self.modules_per_zone = 7  # i.e. a 7x7 group of modules
        else:
            self.modules_per_zone = 5

        total_qr_image_width = (self.num_qr_border_modules + self.num_modules + self.num_qr_border_modules) * self.pixels_per_module
        qr = QR()
        self.qr_image: Image = qr.qrimage(
            self.qr_data,
            width=total_qr_image_width,
            height=total_qr_image_width,  # QR image is always square
            border=self.num_qr_border_modules,
            style=QR.STYLE__ROUNDED
        # ).convert("RGBA")
        )

        # Render gridlines over the QR code but don't draw on its external white border
        qr_image_draw = ImageDraw.Draw(self.qr_image)
        for i in range(self.num_qr_border_modules, math.floor(self.qr_image.width/self.pixels_per_module) - self.num_qr_border_modules):
            qr_image_draw.line((i * self.pixels_per_module, self.num_qr_border_modules * self.pixels_per_module, i * self.pixels_per_module, self.qr_image.height - self.num_qr_border_modules * self.pixels_per_module), fill="#bbb")
            qr_image_draw.line((self.num_qr_border_modules * self.pixels_per_module, i * self.pixels_per_module, self.qr_image.width - self.num_qr_border_modules * self.pixels_per_module, i * self.pixels_per_module), fill="#bbb")

        # Make a blank semi-transparent image for the overlay, initially across the
        # entire canvas.
        mask_rgba = (0, 0, 0, 226)
        self.zone_mask = Image.new("RGBA", (self.canvas_width, self.canvas_height), mask_rgba)
        zone_mask_draw = ImageDraw.Draw(self.zone_mask)

        # Now punch a hole in the center of the mask to highlight the current zone with
        # an accent outline.
        # The `zone_mask_offset_*` vars are the top left xy coords of the mask.
        self.zone_mask_offset_x = int((self.canvas_width - (self.modules_per_zone * self.pixels_per_module))/2)
        self.zone_mask_offset_y = int((self.canvas_height - (self.modules_per_zone * self.pixels_per_module))/2)
        zone_mask_draw.rectangle(
            (
                self.zone_mask_offset_x,
                self.zone_mask_offset_y,
                self.canvas_width - self.zone_mask_offset_x,
                self.canvas_height - self.zone_mask_offset_y
            ),
            fill=(255, 255, 255, 0),  # fully transparent mask area
            outline=GUIConstants.ACCENT_COLOR,
            width=1
        )

        msg = "click to exit"
        font = Fonts.get_font(GUIConstants.BODY_FONT_NAME, GUIConstants.BODY_FONT_SIZE)
        (left, top, right, bottom) = font.getbbox(msg, anchor="ls")
        msg_height = -1 * top + GUIConstants.COMPONENT_PADDING
        msg_width = right + 2*GUIConstants.COMPONENT_PADDING
        zone_mask_draw.rectangle(
            (
                int((self.canvas_width - msg_width)/2),
                self.canvas_height - msg_height,
                int((self.canvas_width + msg_width)/2),
                self.canvas_height
            ),
            fill=GUIConstants.BACKGROUND_COLOR,
        )
        zone_mask_draw.text(
            (int(self.canvas_width/2), self.canvas_height - int(GUIConstants.COMPONENT_PADDING/2)),
            msg,
            fill=GUIConstants.BODY_FONT_COLOR,
            font=font,
            anchor="ms"  # Middle, baSeline
        )



    def draw_zone_labels(self):
        # Create overlay for zone labels (e.g. "D-5")
        # TODO: Discuss w/translators if these zone labels need to be translated; would
        # trigger a secondary need to have translated SeedQR printable templates as well. 
        zone_labels_x = ["1", "2", "3", "4", "5", "6"]
        zone_labels_y = ["A", "B", "C", "D", "E", "F"]

        zone_labels = Image.new("RGBA", (self.canvas_width, self.canvas_height), (255,255,255,0))
        zone_labels_draw = ImageDraw.Draw(zone_labels)
        zone_labels_draw.rectangle((self.zone_mask_offset_x, 0, self.canvas_width - self.zone_mask_offset_x, self.pixels_per_module), fill=GUIConstants.ACCENT_COLOR)
        zone_labels_draw.rectangle((0, self.zone_mask_offset_y, self.pixels_per_module, self.canvas_height - self.zone_mask_offset_y), fill=GUIConstants.ACCENT_COLOR)

        label_font = Fonts.get_font(GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME, 28)
        x_label = zone_labels_x[self.cur_zone_x]
        (left, top, right, bottom) = label_font.getbbox(x_label, anchor="ls")
        x_label_height = -1 * top

        zone_labels_draw.text(
            (int(self.canvas_width/2), self.pixels_per_module - int((self.pixels_per_module - x_label_height)/2)),
            text=x_label,
            fill=GUIConstants.BUTTON_SELECTED_FONT_COLOR,
            font=label_font,
            anchor="ms",  # Middle, baSeline
        )

        y_label = zone_labels_y[self.cur_zone_y]
        (left, top, right, bottom) = label_font.getbbox(y_label, anchor="ls")
        y_label_height = -1 * top
        zone_labels_draw.text(
            (int(self.pixels_per_module/2), int((self.canvas_height + y_label_height) / 2)),
            text=y_label,
            fill=GUIConstants.BUTTON_SELECTED_FONT_COLOR,
            font=label_font,
            anchor="ms",  # Middle, baSeline
        )

        return zone_labels


    def _render(self):
        # Track our current zone-level (macro-module) position and our actual pixel
        # coordinates as we pan around across the QR code image.
        self.cur_zone_x = self.initial_zone_x
        self.cur_zone_y = self.initial_zone_y
        self.cur_pixel_x = (self.cur_zone_x * self.modules_per_zone * self.pixels_per_module) + self.num_qr_border_modules * self.pixels_per_module - self.zone_mask_offset_x
        self.cur_pixel_y = (self.cur_zone_y * self.modules_per_zone * self.pixels_per_module) + self.num_qr_border_modules * self.pixels_per_module - self.zone_mask_offset_y
        self.next_pixel_x = self.cur_pixel_x
        self.next_pixel_y = self.cur_pixel_y

        zone_labels = self.draw_zone_labels()

        self.renderer.show_image(
            self.qr_image.crop((self.cur_pixel_x, self.cur_pixel_y, self.cur_pixel_x + self.canvas_width, self.cur_pixel_y + self.canvas_height)),
            alpha_overlay=Image.alpha_composite(self.zone_mask, zone_labels)
        )


    def _run(self):
        while True:
            input = self.hw_inputs.wait_for(HardwareButtonsConstants.KEYS__LEFT_RIGHT_UP_DOWN + HardwareButtonsConstants.KEYS__ANYCLICK)

            if input in HardwareButtonsConstants.KEYS__ANYCLICK:
                # User clicked to exit
                return

            elif input == HardwareButtonsConstants.KEY_RIGHT and self.cur_zone_x + 1 < math.ceil(self.num_modules/self.modules_per_zone):
                self.next_pixel_x = self.cur_pixel_x + self.modules_per_zone * self.pixels_per_module
                self.cur_zone_x += 1

            elif input == HardwareButtonsConstants.KEY_LEFT and self.cur_zone_x - 1 >= 0:
                self.next_pixel_x = self.cur_pixel_x - self.modules_per_zone * self.pixels_per_module
                self.cur_zone_x -= 1

            elif input == HardwareButtonsConstants.KEY_DOWN and self.cur_zone_y + 1 < math.ceil(self.num_modules/self.modules_per_zone):
                self.next_pixel_y = self.cur_pixel_y + self.modules_per_zone * self.pixels_per_module
                self.cur_zone_y += 1

            elif input == HardwareButtonsConstants.KEY_UP and self.cur_zone_y - 1 >= 0:
                self.next_pixel_y = self.cur_pixel_y - self.modules_per_zone * self.pixels_per_module
                self.cur_zone_y -= 1

            else:
                # User selected a direction that we can't advance any further
                continue

            # Create overlay for zone labels (e.g. "D-5")
            zone_labels = self.draw_zone_labels()

            with self.renderer.lock:
                self.renderer.show_image_pan(
                    self.qr_image,
                    self.cur_pixel_x, self.cur_pixel_y, self.next_pixel_x, self.next_pixel_y,
                    rate=self.pixels_per_module,
                    alpha_overlay=Image.alpha_composite(self.zone_mask, zone_labels)
                )
            self.cur_pixel_x = self.next_pixel_x
            self.cur_pixel_y = self.next_pixel_y

@dataclass
class AddressScreen(BaseTopNavScreen):
    address: str = None
    
    def __post_init__(self):
        super().__post_init__()
        
        content_y = self.top_nav.height + GUIConstants.COMPONENT_PADDING
        self.components.append(
            RoundedTextArea(
                text=self.address,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=content_y,
                width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
                height=self.canvas_height - content_y - 2 * GUIConstants.COMPONENT_PADDING,
                fill_color=GUIConstants.INACTIVE_COLOR,
                is_text_centered=True,
                treat_chars_as_words=True,
            )
        )

@dataclass
class GenerateAddressScreen(BaseTopNavScreen):
    def __post_init__(self):

        self.show_back_button = False

        super().__post_init__()

        #
        self.title_text = "Introduce Address Index"

        # Track the selected address type (default to Standard)
        self.address_type = "standard"

        # Store the user's input index
        self.user_input = ""

        # add title text
        self.title_text_display = TextArea(
            text=self.title_text,
            screen_x=GUIConstants.COMPONENT_PADDING,
            screen_y=GUIConstants.COMPONENT_PADDING * 2,
        )

        # Set up the keyboard params
        self.right_panel_buttons_width = 118

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
            text="Standard",
            is_text_centered=False,
            font_name=GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME,
            font_size=GUIConstants.BUTTON_FONT_SIZE + 4,
            width=self.right_panel_buttons_width,
            screen_x=hw_button_x,
            screen_y=hw_button_y
            - 3 * GUIConstants.COMPONENT_PADDING
            - GUIConstants.BUTTON_HEIGHT,
            is_scrollable_text=False,
            is_selected=True,  # Standard is selected by default
        )

        self.hw_button2 = Button(
            text="Cashtoken",
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
            text="Back",
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
        self.hw_button1.is_selected = self.address_type == "standard"
        self.hw_button2.is_selected = self.address_type == "cashtoken"

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
                    # Standard button pressed
                    self.address_type = "standard"
                    self._render()
                    continue

                elif input == HardwareButtonsConstants.KEY2:
                    # Cashtoken button pressed
                    self.address_type = "cashtoken"
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
