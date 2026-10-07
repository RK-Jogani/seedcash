import math
import time

from dataclasses import dataclass
from gettext import gettext as _
from gettext import ngettext
from PIL import Image, ImageDraw, ImageFilter

from seedcash.gui.components import (
    BchAmount,
    Category,
    TokenAmount,
    Icon,
    FormattedAddress,
    GUIConstants,
    Fonts,
    SeedCashIconsConstants,
    TextArea,
    RoundedTextArea,
    calc_bezier_curve,
    linear_interp,
    load_image,
)
from seedcash.gui.renderer import Renderer
from seedcash.models.threads import BaseThread

from .screen import (
    ButtonOption,
    SeedCashButtonListWithNav,
    ScrollableCardConfirmScreen,
)




@dataclass
class PSBTOverviewScreen(SeedCashButtonListWithNav):
    inputs_amount: int = 0
    fee_amount: int = 0
    input_count: int = 0
    destination_addresses: list[str] = None
    has_op_return: bool = False
    category: Category = None
    is_genesis: bool = False

    def __post_init__(self):

        # Customize defaults
        self.title = _("Review PSBT")
        self.is_bottom_list = True
        self.is_button_text_centered = True

        self.button_data = [ButtonOption("Next")]

        super().__post_init__()

        # This screen can take a while to load while parsing the PSBT
        self.show_loading_screen = True

        # Prep the headline amount being spent in large callout
        icon_text_lines_y = self.top_nav.height + GUIConstants.COMPONENT_PADDING

        if self.is_genesis:
            pass
        elif self.category:    
            self.components.append(
                TokenAmount(
                    amount=self.inputs_amount,
                    category=self.category,
                    screen_y=icon_text_lines_y,
                )
            )
        else:
            self.components.append(
                BchAmount(
                    total_sats=self.inputs_amount,
                    screen_y=icon_text_lines_y,
                )
            )

        # Prep the transaction flow chart
        self.chart_x = 0
        if self.is_genesis:
            self.chart_y = (self.canvas_height) // 2 - self.top_nav.height - 3 * GUIConstants.COMPONENT_PADDING
        else:
            self.chart_y = (
                self.components[-1].screen_y
                + self.components[-1].height
                + int(GUIConstants.COMPONENT_PADDING / 2))
        
        chart_height = (
            self.buttons[0].screen_y - self.chart_y - GUIConstants.COMPONENT_PADDING
        )

        # We need to supersample the whole panel so that small/thin elements render clearly.
        ssf = 4  # super-sampling factor

        # Set up our temp supersampled rendering surface
        image = Image.new(
            "RGB",
            (self.canvas_width * ssf, chart_height * ssf),
            GUIConstants.BACKGROUND_COLOR,
        )
        draw = ImageDraw.Draw(image)

        font_size = GUIConstants.BODY_FONT_MIN_SIZE * ssf
        font = Fonts.get_font(GUIConstants.BODY_FONT_NAME, font_size)

        left, top, right, bottom = font.getbbox(
            text="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890[]",
            anchor="lt",
        )
        chart_text_height = bottom
        vertical_center = int(image.height / 2)
        # Supersampling renders thin elements poorly if they land on an even line before scaling down
        if vertical_center % 2 == 1:
            vertical_center += 1

        association_line_color = "#666"
        association_line_width = 3 * ssf
        curve_steps = 4
        chart_font_color = "#ddd"

        # First calculate how wide the inputs col will be
        inputs_column = []
        if self.input_count == 1:
            inputs_column.append(_("1 input" if self.inputs_amount > 0 else "Genesis"))
        elif self.input_count > 5:
            inputs_column.append(_("input 1"))
            inputs_column.append(_("input 2"))
            inputs_column.append(_("[ ... ]"))
            inputs_column.append(_("input {}").format(self.input_count - 1))
            inputs_column.append(_("input {}").format(self.input_count))
        else:
            for i in range(0, self.input_count):
                inputs_column.append(_("input {}").format(i + 1))

        max_inputs_text_width = 0
        for input in inputs_column:
            left, top, right, bottom = font.getbbox(input)
            tw, th = right - left, bottom - top
            max_inputs_text_width = max(tw, max_inputs_text_width)

        # Given how wide we want our curves on each side to be...
        curve_width = 4 * GUIConstants.COMPONENT_PADDING * ssf

        # First, try to show as much of the destination addresses as possible
        # We'll try truncation from longest to shortest to maximize visibility
        def calculate_destination_col_width(truncate_at: int = 0):
            def display_destination_addr(addr):
                if addr.startswith("bitcoincash:"):
                    return addr[len("bitcoincash:") :]
                return addr

            def truncate_destination_addr(addr):
                addr = display_destination_addr(addr)
                if len(addr) <= truncate_at + len(_("...")):
                    return addr
                return addr[:truncate_at] + _("...")

            destination_column = []

            if len(self.destination_addresses) <= 3:
                for addr in self.destination_addresses:
                    destination_column.append(truncate_destination_addr(addr))
            else:
                destination_column.append(_("recipient 1"))
                destination_column.append(_("[ ... ]"))
                destination_column.append(
                    _("recipient {}").format(len(self.destination_addresses))
                )
            
            if self.fee_amount > 0:
                destination_column.append(_("fee"))

            if self.has_op_return:
                destination_column.append(_("OP_RETURN"))

            max_destination_text_width = 0
            for destination in destination_column:
                left, top, right, bottom = font.getbbox(destination)
                tw, th = right - left, bottom - top
                max_destination_text_width = max(tw, max_destination_text_width)

            return (max_destination_text_width, destination_column)

        # Calculate the maximum available width for the destination column
        # We need to leave room for: inputs + padding + curve + center_bar + curve + padding
        fixed_width_parts = (
            max_inputs_text_width
            + int(GUIConstants.COMPONENT_PADDING * ssf / 4)
            + curve_width
            + (2 * GUIConstants.COMPONENT_PADDING * ssf)  # Center bar
            + curve_width
            + int(GUIConstants.COMPONENT_PADDING * ssf / 4)
        )
        
        max_destination_width = image.width - fixed_width_parts
        
        # Try to show as many characters as possible by testing different truncation lengths
        destination_text_width = None
        destination_column = None
        
        # Start with no truncation and work our way down
        for truncate_at in range(5, 3, -1):
            new_width, new_col_text = calculate_destination_col_width(truncate_at=truncate_at)
            if new_width <= max_destination_width:
                destination_text_width = new_width
                destination_column = new_col_text
                break
        
        # If even the shortest truncation doesn't fit, just use the shortest
        if destination_text_width is None:
            destination_text_width, destination_column = calculate_destination_col_width(truncate_at=3)

        # Calculate total content width for centering
        total_content_width = (
            max_inputs_text_width
            + int(GUIConstants.COMPONENT_PADDING * ssf / 4)
            + curve_width
            + (2 * GUIConstants.COMPONENT_PADDING * ssf)  # Center bar
            + curve_width
            + int(GUIConstants.COMPONENT_PADDING * ssf / 4)
            + destination_text_width
        )

        # Calculate the start x position to center everything
        content_start_x = (image.width - total_content_width) // 2

        # Now calculate all positions from the centered start
        inputs_x = content_start_x
        center_bar_x = (
            content_start_x
            + max_inputs_text_width
            + int(GUIConstants.COMPONENT_PADDING * ssf / 4)
            + curve_width
        )

        # Center bar has a fixed width (not stretched)
        center_bar_width = 2 * GUIConstants.COMPONENT_PADDING * ssf

        destination_col_x = (
            center_bar_x
            + center_bar_width
            + curve_width
            + int(GUIConstants.COMPONENT_PADDING * ssf / 4)
        )

        # Position each input row
        num_rendered_inputs = len(inputs_column)
        if self.input_count == 1:
            inputs_y = vertical_center - int(chart_text_height / 2)
            inputs_y_spacing = 0
        else:
            inputs_y = int(
                (image.height - num_rendered_inputs * chart_text_height)
                / (num_rendered_inputs + 1)
            )
            inputs_y_spacing = inputs_y + chart_text_height

        # Don't render lines from an odd number
        if inputs_y % 2 == 1:
            inputs_y += 1
        if inputs_y_spacing % 2 == 1:
            inputs_y_spacing += 1

        inputs_conjunction_x = center_bar_x

        input_curves = []
        for input in inputs_column:
            # Calculate right-justified input display
            left, top, right, bottom = font.getbbox(input)
            tw, th = right - left, bottom - top
            cur_x = inputs_x + max_inputs_text_width - tw
            draw.text(
                (cur_x, inputs_y),
                text=input,
                font=font,
                fill=chart_font_color,
                anchor="lt",
            )

            # Render the association line to the conjunction point
            start_pt = (
                inputs_x
                + max_inputs_text_width
                + int(GUIConstants.COMPONENT_PADDING * ssf / 4),
                inputs_y + int(chart_text_height / 2),
            )
            conjunction_pt = (inputs_conjunction_x, vertical_center)
            mid_pt = (
                int(start_pt[0] * 0.5 + conjunction_pt[0] * 0.5),
                int(start_pt[1] * 0.5 + conjunction_pt[1] * 0.5),
            )

            if len(inputs_column) == 1:
                bezier_points = [
                    start_pt,
                    linear_interp(start_pt, conjunction_pt, 0.33),
                    linear_interp(start_pt, conjunction_pt, 0.66),
                    conjunction_pt,
                ]
            else:
                bezier_points = calc_bezier_curve(
                    start_pt, (mid_pt[0], start_pt[1]), mid_pt, curve_steps
                )
                bezier_points.pop()
                bezier_points += calc_bezier_curve(
                    mid_pt, (mid_pt[0], conjunction_pt[1]), conjunction_pt, curve_steps
                )

            input_curves.append(bezier_points)

            prev_pt = bezier_points[0]
            for pt in bezier_points[1:]:
                draw.line(
                    (prev_pt[0], prev_pt[1], pt[0], pt[1]),
                    fill=association_line_color,
                    width=association_line_width + 1,
                    joint="curve",
                )
                prev_pt = pt

            inputs_y += inputs_y_spacing

        # Render center bar
        draw.line(
            (
                center_bar_x,
                vertical_center,
                center_bar_x + center_bar_width,
                vertical_center,
            ),
            fill=association_line_color,
            width=association_line_width,
        )

        # Position each destination
        num_rendered_destinations = len(destination_column)
        if num_rendered_destinations == 1:
            destination_y = vertical_center - int(chart_text_height / 2)
            destination_y_spacing = 0
        else:
            destination_y = int(
                (image.height - num_rendered_destinations * chart_text_height)
                / (num_rendered_destinations + 1)
            )
            destination_y_spacing = destination_y + chart_text_height

        # Don't render lines from an odd number
        if destination_y % 2 == 1:
            destination_y += 1
        if destination_y_spacing % 2 == 1:
            destination_y_spacing += 1

        destination_conjunction_x = center_bar_x + center_bar_width
        recipients_text_x = destination_col_x

        output_curves = []
        for destination in destination_column:
            draw.text(
                (recipients_text_x, destination_y),
                text=destination,
                font=font,
                fill=chart_font_color,
                anchor="lt",
            )

            # Render the association line from the conjunction point
            conjunction_pt = (destination_conjunction_x, vertical_center)
            end_pt = (
                conjunction_pt[0] + curve_width,
                destination_y + int(chart_text_height / 2),
            )
            mid_pt = (
                int(conjunction_pt[0] * 0.5 + end_pt[0] * 0.5),
                int(conjunction_pt[1] * 0.5 + end_pt[1] * 0.5),
            )

            bezier_points = calc_bezier_curve(
                conjunction_pt, (mid_pt[0], conjunction_pt[1]), mid_pt, curve_steps
            )
            bezier_points.pop()

            curve_bias = 1.0
            bezier_points += calc_bezier_curve(
                mid_pt,
                (
                    int(mid_pt[0] * curve_bias + end_pt[0] * (1.0 - curve_bias)),
                    end_pt[1],
                ),
                end_pt,
                curve_steps,
            )

            output_curves.append(bezier_points)

            prev_pt = bezier_points[0]
            for pt in bezier_points[1:]:
                draw.line(
                    (prev_pt[0], prev_pt[1], pt[0], pt[1]),
                    fill=association_line_color,
                    width=association_line_width + 1,
                    joint="curve",
                )
                prev_pt = pt

            destination_y += destination_y_spacing

        # Resize to target and sharpen final image
        image = image.resize(
            (self.canvas_width, chart_height), Image.Resampling.LANCZOS
        )
        self.paste_images.append(
            (image.filter(ImageFilter.SHARPEN), (self.chart_x, self.chart_y))
        )

        # Pass input and output curves to the animation thread
        self.threads.append(
            PSBTOverviewScreen.TxExplorerAnimationThread(
                pulse_color=self.selected_color,
                inputs=input_curves,
                outputs=output_curves,
                supersampling_factor=ssf,
                offset_y=self.chart_y,
                renderer=self.renderer,
            )
        )

    class TxExplorerAnimationThread(BaseThread):
        def __init__(
            self, pulse_color, inputs, outputs, supersampling_factor, offset_y, renderer: Renderer
        ):
            super().__init__()
            self.pulse_color = pulse_color
            ssf = supersampling_factor
            self.inputs = [
                [(int(i[0] / ssf), int(i[1] / ssf + offset_y)) for i in curve]
                for curve in inputs
            ]
            self.outputs = [
                [(int(i[0] / ssf), int(i[1] / ssf + offset_y)) for i in curve]
                for curve in outputs
            ]
            self.renderer = renderer

        def run(self):
            pulse_color = self.pulse_color
            reset_color = "#666"
            line_width = 3

            pulses = []

            start_pt = self.inputs[0][-1]
            end_pt = self.outputs[0][0]
            if start_pt == end_pt:
                center_bar_pts = [end_pt, self.outputs[0][1]]
            else:
                center_bar_pts = [
                    start_pt,
                    linear_interp(start_pt, end_pt, 0.25),
                    linear_interp(start_pt, end_pt, 0.50),
                    linear_interp(start_pt, end_pt, 0.75),
                    end_pt,
                ]

            def draw_line_segment(curves, i, j, color):
                for points in curves:
                    pt1 = points[i]
                    pt2 = points[j]
                    self.renderer.draw.line(
                        (pt1[0], pt1[1], pt2[0], pt2[1]), fill=color, width=line_width
                    )

            prev_color = reset_color
            while self.keep_running:
                with self.renderer.lock:
                    if not pulses or (
                        prev_color == pulse_color and pulses[-1][0] == 10
                    ):
                        if prev_color == pulse_color:
                            pulses.append([0, reset_color])
                        else:
                            pulses.append([0, pulse_color])
                        prev_color = pulses[-1][1]

                    for pulse_num, pulse in enumerate(pulses):
                        i = pulse[0]
                        color = pulse[1]
                        if i < len(self.inputs[0]) - 1:
                            draw_line_segment(self.inputs, i, i + 1, color)
                        elif i < len(self.inputs[0]) + len(center_bar_pts) - 2:
                            index = i - len(self.inputs[0]) + 1
                            draw_line_segment([center_bar_pts], index, index + 1, color)
                        elif (
                            i
                            < len(self.inputs[0])
                            + len(center_bar_pts)
                            - 2
                            + len(self.outputs[0])
                            - 1
                        ):
                            index = i - (len(self.inputs[0]) + len(center_bar_pts) - 2)
                            draw_line_segment(self.outputs, index, index + 1, color)
                        else:
                            del pulses[pulse_num]
                            continue

                        pulse[0] += 1

                    self.renderer.show_image()

                time.sleep(0.02)

@dataclass
class PSBTMathScreen(SeedCashButtonListWithNav):
    input_amount: int = 0
    input_count: int = 0
    spend_amount: int = 0
    output_count: int = 0
    fee_amount: int = 0

    def __post_init__(self):
        # Customize defaults
        self.title = _("PSBT Math")
        self.is_button_text_centered = True
        self.button_data = [ButtonOption("Review Recipients")]
        self.is_bottom_list = True

        super().__post_init__()

       
        self.input_amount = f"{self.input_amount:,}"
        self.spend_amount = f"{self.spend_amount:,}"
        self.fee_amount = f"{self.fee_amount:,}"

        # Align the digits - pad all amounts to same width
        longest_amount = max(
            len(self.input_amount),
            len(self.spend_amount),
            len(self.fee_amount),
        )
        
        # Right-pad amounts so they're all the same width
        # This ensures digits align vertically
        if len(self.input_amount) < longest_amount:
            self.input_amount = (
                " " * (longest_amount - len(self.input_amount)) + self.input_amount
            )

        if len(self.spend_amount) < longest_amount:
            self.spend_amount = (
                " " * (longest_amount - len(self.spend_amount)) + self.spend_amount
            )

        if len(self.fee_amount) < longest_amount:
            self.fee_amount = (
                " " * (longest_amount - len(self.fee_amount)) + self.fee_amount
            )

        # Render the info to temp Image
        body_width = self.canvas_width - 2 * GUIConstants.EDGE_PADDING
        body_height = (
            self.buttons[0].screen_y
            - self.top_nav.height
            - 2 * GUIConstants.COMPONENT_PADDING
        )
        ssf = 2  # Super-sampling factor
        image = Image.new("RGB", (body_width * ssf, body_height * ssf))
        draw = ImageDraw.Draw(image)

        body_font = Fonts.get_font(
            GUIConstants.BODY_FONT_NAME, (GUIConstants.BODY_FONT_SIZE) * ssf
        )
        fixed_width_font = Fonts.get_font(
            GUIConstants.FIXED_WIDTH_FONT_NAME,
            (GUIConstants.BODY_FONT_SIZE + 6) * ssf,
        )
        
        # Get dimensions for the amount text
        left, top, right, bottom = fixed_width_font.getbbox("0" * longest_amount + "0")
        digits_width, digits_height = right - left, bottom - top
        
        # Get dimensions for the info text
        info_texts = [
            ngettext("input", "inputs", self.input_count) if self.input_count > 0 else "",
            ngettext("output", "outputs", self.output_count) if self.output_count > 0 else "",
            _("fee")
        ]
        max_info_width = 0
        for info in info_texts:
            if info:
                left, top, right, bottom = body_font.getbbox(info)
                max_info_width = max(max_info_width, right - left)

        # Calculate total width of amount + info
        spacing = 3 * ssf  # Space between amount and info
        total_line_width = digits_width + spacing + max_info_width
        
        # Calculate starting X to center the entire block
        block_start_x = (image.width - total_line_width) // 2
        
        # Draw each line of the equation
        cur_y = 0

        def render_amount(
            cur_y, amount_str, info_text, info_text_color=GUIConstants.BODY_FONT_COLOR
        ):
            # Draw amount at the same X position (aligned)
            draw.text(
                (block_start_x, cur_y),
                text=amount_str,
                font=fixed_width_font,
                fill=GUIConstants.BODY_FONT_COLOR,
            )
            
            # Draw info text after the amount with spacing
            if info_text:
                draw.text(
                    (block_start_x + digits_width + spacing, cur_y),
                    text=info_text,
                    font=body_font,
                    fill=info_text_color,
                )

        # Render each line
        render_amount(
            cur_y,
            f" {self.input_amount}",
            info_text=ngettext("input", "inputs", self.input_count),
        )

        # spend_amount will be zero on self-transfers; only display when there's an
        # external recipient.
        if self.output_count > 0:
            cur_y += digits_height + GUIConstants.BODY_LINE_SPACING * ssf
            render_amount(
                cur_y,
                f"-{self.spend_amount}",
                info_text=ngettext("output", "outputs", self.output_count),
            )

        cur_y += digits_height + GUIConstants.BODY_LINE_SPACING * ssf
        # Draw separator line (centered)
        line_y = cur_y
        draw.line(
            (block_start_x, line_y, block_start_x + total_line_width, line_y), 
            fill=GUIConstants.BODY_FONT_COLOR, 
            width=1
        )

        cur_y += ssf
        render_amount(
            cur_y,
            f" {self.fee_amount}",
            info_text=_("fee"),
        )

        # Resize to target and sharpen final image
        image = image.resize((body_width, body_height), Image.Resampling.LANCZOS)
        self.paste_images.append(
            (
                image.filter(ImageFilter.SHARPEN),
                (
                    GUIConstants.EDGE_PADDING,
                    self.top_nav.height + GUIConstants.COMPONENT_PADDING,
                ),
            )
        )

@dataclass
class PSBTAddressDetailsScreen(SeedCashButtonListWithNav):
    address: str = None
    amount: int = 0
    category: Category = None 

    def __post_init__(self):
        # Customize defaults
        self.is_bottom_list = True
        self.is_button_text_centered = True
        super().__post_init__()

        center_img_height = self.buttons[0].screen_y - self.top_nav.height

        # Figuring out how to vertically center the sats and the address is
        # difficult so we just render to a temp image and paste it in place.
        center_img = Image.new(
            "RGB", (self.canvas_width, center_img_height), GUIConstants.BACKGROUND_COLOR
        )
        draw = ImageDraw.Draw(center_img)

        if self.category:
            _amount = TokenAmount(
                image_draw=draw,
                canvas=center_img,
                amount=self.amount,
                category=self.category,
                screen_y=int(GUIConstants.COMPONENT_PADDING / 2)
            )
        else:
            _amount = BchAmount(
                image_draw=draw,
                canvas=center_img,
                total_sats=self.amount,
                screen_y=int(GUIConstants.COMPONENT_PADDING / 2),
            )

        formatted_address = FormattedAddress(
            image_draw=draw,
            canvas=center_img,
            width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=_amount.height + GUIConstants.COMPONENT_PADDING,
            font_size=24,
            font_accent_color=self.selected_color,
            address=self.address,
        )

        # Render each to the temp img we passed in
        _amount.render()
        formatted_address.render()

        self.body_img = center_img.crop(
            (
                0,
                0,
                self.canvas_width,
                formatted_address.screen_y + formatted_address.height,
            )
        )
        body_img_y = self.top_nav.height + int(
            (center_img_height - self.body_img.height - GUIConstants.COMPONENT_PADDING)
            / 2
        )

        self.paste_images.append((self.body_img, (0, body_img_y)))

@dataclass
class PSBTOpReturnScreen(ScrollableCardConfirmScreen):
    op_return_data: str = None

    def __post_init__(self):
        self.title = _("Review PSBT")
        self.is_button_text_centered = True
        self.confirm_button_label = _("Next")
        
        op_return_text = TextArea(
            text=self.op_return_data,
            font_size=GUIConstants.TOP_NAV_TITLE_FONT_SIZE,
            font_color=GUIConstants.BODY_FONT_COLOR,
            is_text_centered=False,
            background_color=GUIConstants.TRANSPARENT_COLOR
        )

        self.card_components = [(op_return_text, 0)]
        super().__post_init__()

        
@dataclass
class PSBTFinalizeScreen(SeedCashButtonListWithNav):
    def __post_init__(self):
        # Customize defaults
        self.title = _("Sign PSBT")
        self.is_bottom_list = True
        self.is_button_text_centered = True
        super().__post_init__()

        icon = Icon(
            icon_name=SeedCashIconsConstants.SIGN,
            icon_color=GUIConstants.INFO_COLOR,
            icon_size=GUIConstants.ICON_LARGE_BUTTON_SIZE,
            screen_y=self.top_nav.height + GUIConstants.COMPONENT_PADDING,
        )
        icon.screen_x = int((self.canvas_width - icon.width) / 2)
        self.components.append(icon)

        self.components.append(
            TextArea(
                text=_("Click to sign PSBT"),
                screen_y=icon.screen_y
                + icon.height
                + 2 * GUIConstants.COMPONENT_PADDING,
            )
        )

@dataclass
class PSBTNFTScreen(SeedCashButtonListWithNav):
    category_id: str = None

    def __post_init__(self):
        # Customize defaults
        self.title = _("Review PSBT")
        self.is_bottom_list = True
        self.is_button_text_centered = True
        super().__post_init__()
        
        # collection TODO: For now we have unkown we will add collection in future
        y_offset = self.top_nav.height + GUIConstants.COMPONENT_PADDING
        
        self.components.append(
            TextArea(
                text="Collection",
                font_size=GUIConstants.BODY_FONT_SIZE - 4,
                is_text_centered=False,
                screen_y=y_offset,
            )
        )
        y_offset += GUIConstants.BODY_FONT_SIZE + GUIConstants.COMPONENT_PADDING // 2
        self.components.append(
            RoundedTextArea(
                text="Unknown",
                font_size=GUIConstants.BODY_FONT_SIZE - 2,
                is_text_centered=False,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=y_offset,
            )
        )

        # category
        y_offset += GUIConstants.BODY_FONT_SIZE + 2 * GUIConstants.COMPONENT_PADDING
        self.components.append(
            TextArea(
                text="Category ID",
                font_size=GUIConstants.BODY_FONT_SIZE - 4,
                is_text_centered=False,
                screen_y=y_offset,
            )
        )

        y_offset += GUIConstants.BODY_FONT_SIZE + GUIConstants.COMPONENT_PADDING // 2
        self.components.append(
            RoundedTextArea(
                text=self.category_id,
                font_size=GUIConstants.BODY_FONT_SIZE - 2,
                is_text_centered=False,
                treat_chars_as_words=True,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=y_offset,
            )
        )

@dataclass
class PSBTNFTDetailsScreen(SeedCashButtonListWithNav):
    """
    Same constructor signature (output_num, nft_capability, nft_commitment).
    A static card between the top nav and the Next button. Its background
    image depends on the NFT type (gold for minting, graphite for none,
    mutable and anything else), with the heading, Type and Commitment drawn
    on top.
    """

    # NFT type to card background theme. Any other type uses graphite.
    NFT_CARD_THEMES = {"minting": "gold"}
    NFT_CARD_DEFAULT_THEME = "graphite"
    NFT_CARD_FALLBACK_COLOR = (38, 38, 48)

    output_num: int = None
    nft_capability: str = None
    nft_commitment: str = None

    def __post_init__(self):
        self.title = _("Review PSBT")
        self.is_bottom_list = True
        self.is_button_text_centered = True
        self.button_data = [ButtonOption(_("Next"))]

        super().__post_init__()      # builds top nav, the Next button, paste_images

        # The card fills the space between the top nav and the Next button
        self.card_x = GUIConstants.EDGE_PADDING
        self.card_y = self.top_nav.height
        self.card_width = self.canvas_width - 2 * GUIConstants.EDGE_PADDING
        self.card_height = (
            self.buttons[0].screen_y - self.card_y - GUIConstants.COMPONENT_PADDING
        )

        card = self._load_card_background()
        self._draw_card_text(card)
        self.paste_images.append((card.convert("RGB"), (self.card_x, self.card_y)))

    def _load_card_background(self) -> Image.Image:
        """Background PNG for this NFT type. The file name carries the card
        size, so it must match the generated files."""
        theme = self.NFT_CARD_THEMES.get(str(self.nft_capability).lower(), self.NFT_CARD_DEFAULT_THEME)
        name = f"nft_card_{theme}.png"
        try:
            return load_image(name, "img").convert("RGBA")
        except Exception:
            # Missing file or wrong card size: plain rounded card instead
            card = Image.new("RGBA", (self.card_width, self.card_height), (0, 0, 0, 255))
            ImageDraw.Draw(card).rounded_rectangle(
                (0, 0, self.card_width - 1, self.card_height - 1),
                radius=16,
                fill=self.NFT_CARD_FALLBACK_COLOR,
            )
            return card

    def _draw_card_text(self, card: Image.Image):
        """Draw the heading and the label / value pairs onto the card.
        Text goes on a transparent layer first, so the background pixels
        under it are never overwritten."""
        layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)

        inner = 2 * GUIConstants.COMPONENT_PADDING
        text_width = card.width - 2 * inner

        def text(value, size, centered=False):
            return TextArea(
                image_draw=layer_draw,
                canvas=layer,
                text=value,
                width=text_width,
                edge_padding=0,
                font_size=size,
                font_color=GUIConstants.BODY_FONT_COLOR,
                is_text_centered=centered,
                background_color=GUIConstants.TRANSPARENT_COLOR,
            )

        gap = GUIConstants.COMPONENT_PADDING
        rows = [
            (text(f"NFT #{self.output_num}", GUIConstants.TOP_NAV_TITLE_FONT_SIZE), gap * 2),
            (text(_("Type"), GUIConstants.BODY_FONT_SIZE - 4), gap // 2),
            (text(self.nft_capability, GUIConstants.BODY_FONT_SIZE - 2), gap * 2),
        ]

        # nft_commitment is an empty string when there is nothing to show;
        # keep that section out of the card entirely in that case.
        if self.nft_commitment != "":
            rows += [
                (text(_("Commitment"), GUIConstants.BODY_FONT_SIZE - 4), gap // 2),
                (text(self.nft_commitment, GUIConstants.BODY_FONT_SIZE - 2), 0),
            ]

        y = inner
        for component, gap_after in rows:
            component.screen_x = inner
            component.screen_y = y
            component.render()
            y += component.height + gap_after

        card.alpha_composite(layer)

@dataclass
class PSBTNFTAddressScreen(SeedCashButtonListWithNav):
    destination_addr: str = None
    index: int = None

    def __post_init__(self):
        self.title = _("Will Send")
        self.is_bottom_list = True
        self.is_button_text_centered = True
        super().__post_init__()

        center_img_height = self.buttons[0].screen_y - self.top_nav.height
        center_img = Image.new("RGB", (self.canvas_width, center_img_height), GUIConstants.BACKGROUND_COLOR)
        draw = ImageDraw.Draw(center_img)

        # ---- Center the "NFT#" label ----
        self.text_font = Fonts.get_font(GUIConstants.FIXED_WIDTH_EMPHASIS_FONT_NAME, 24)
        draw.text(
            (self.canvas_width // 2, 2*GUIConstants.COMPONENT_PADDING),  # <-- center x
            text=f"NFT#{self.index}",
            font=self.text_font,
            fill=GUIConstants.BODY_FONT_COLOR,
            anchor="ms",   # middle baseline (center horizontally, baseline vertical)
        )

        # Address (left‑aligned)
        formatted_address = FormattedAddress(
            image_draw=draw,
            canvas=center_img,
            width=self.canvas_width - 2 * GUIConstants.EDGE_PADDING,
            screen_x=GUIConstants.EDGE_PADDING,
            screen_y=GUIConstants.COMPONENT_PADDING + 30,
            font_size=24,
            font_accent_color=GUIConstants.MUSD_BLUE,
            address=self.destination_addr,
        )
        formatted_address.render()

        # Crop and position as before...
        center_img = center_img.crop(
            (0, 0, self.canvas_width, formatted_address.screen_y + formatted_address.height)
        )
        body_img_y = self.top_nav.height + int(
            (center_img_height - center_img.height - GUIConstants.COMPONENT_PADDING) / 2
        )
        self.paste_images.append((center_img, (0, body_img_y))) 
