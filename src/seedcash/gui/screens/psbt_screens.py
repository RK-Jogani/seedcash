import math
import time

from dataclasses import dataclass
from gettext import gettext as _
from gettext import ngettext
from PIL import Image, ImageDraw, ImageFilter

from seedcash.gui.components import (
    BchAmount,
    Category,
    categories,
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
)
from seedcash.gui.renderer import Renderer
from seedcash.hardware.buttons import HardwareButtonsConstants
from seedcash.models.threads import BaseThread

from .screen import (
    ButtonListScreen,
    BaseTopNavScreen,
    ButtonOption,
    Button,
    RET_CODE__BACK_BUTTON,
    RET_CODE__CHECK_BUTTON,
)


@dataclass
class PSBTButtonListScreen(BaseTopNavScreen, ButtonListScreen):
    def _run(self):
        while True:
            ret = self._run_callback()
            if ret is not None:
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
                    if self.top_nav.show_back_button or self.top_nav.show_check_button:
                        self.buttons[self.selected_button].is_selected = False
                        self.buttons[self.selected_button].render()
                        self.top_nav.is_selected = True
                        self.top_nav.render_buttons()

                elif user_input == HardwareButtonsConstants.KEY_UP:
                    if self.top_nav.is_selected:
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
                        if self.top_nav.show_check_button:
                            if self.top_nav.right_button.is_selected:
                                return RET_CODE__CHECK_BUTTON
                        if self.top_nav.show_back_button:
                            if self.top_nav.left_button.is_selected:
                                return RET_CODE__BACK_BUTTON

                    return self.selected_button

                self.renderer.show_image()


@dataclass
class PSBTOverviewScreen(PSBTButtonListScreen):
    spend_amount: int = 0
    fee_amount: int = 0
    num_inputs: int = 0
    destination_addresses: list[str] = None
    has_op_return: bool = False
    category_id: str = None

    def __post_init__(self):

        # Customize defaults
        self.title = _("Review PSBT")
        self.is_bottom_list = True
        self.is_button_text_centered = True

        for category in categories:
            if category.category_id == self.category_id:
                self.category: Category = category
                break        
        else:
            self.category: Category = Category(
                category_id=self.category_id,
                token_symbol="Unknown",
                decimal=0,
                icon_name=SeedCashIconsConstants.CASHTOKEN,
                icon_color=GUIConstants.ACCENT_COLOR,
            )

        self.button_data = [ButtonOption("Next", button_color=self.category.icon_color)]

        super().__post_init__()

        # This screen can take a while to load while parsing the PSBT
        self.show_loading_screen = True

        # Prep the headline amount being spent in large callout
        icon_text_lines_y = self.top_nav.height + GUIConstants.COMPONENT_PADDING

        if self.category_id:
            self.components.append(
                TokenAmount(
                    amount=self.spend_amount,
                    category=self.category,
                    screen_y=icon_text_lines_y,
                )
            )
        else:
            self.components.append(
                BchAmount(
                    total_sats=self.spend_amount,
                    screen_y=icon_text_lines_y,
                )
            )

        # Prep the transaction flow chart
        self.chart_x = 0
        self.chart_y = (
            self.components[-1].screen_y
            + self.components[-1].height
            + int(GUIConstants.COMPONENT_PADDING / 2)
        )
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
        if self.num_inputs == 1:
            inputs_column.append(_("1 input"))
        elif self.num_inputs > 5:
            inputs_column.append(_("input 1"))
            inputs_column.append(_("input 2"))
            inputs_column.append(_("[ ... ]"))
            inputs_column.append(_("input {}").format(self.num_inputs - 1))
            inputs_column.append(_("input {}").format(self.num_inputs))
        else:
            for i in range(0, self.num_inputs):
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
        if self.num_inputs == 1:
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
                pulse_color=self.category.icon_color,
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
class PSBTMathScreen(PSBTButtonListScreen):
    input_amount: int = 0
    num_inputs: int = 0
    spend_amount: int = 0
    num_outputs: int = 0
    fee_amount: int = 0

    def __post_init__(self):
        # Customize defaults
        self.title = _("PSBT Math")
        self.is_button_text_centered = True
        self.button_data = [ButtonOption("Review Recipients")]
        self.is_bottom_list = True

        super().__post_init__()

        if self.input_amount >= 1e6:
            denomination = _("bch")
            self.input_amount /= 1e6
            self.spend_amount /= 1e6
            self.input_amount = f"{self.input_amount:,.6f}"
            self.spend_amount = f"{self.spend_amount:,.6f}"

            # Note: We keep the fee denominated in sats; just left pad it so it still
            # lines up properly.
            self.fee_amount = f"{self.fee_amount:10}"
        else:
            denomination = _("sats")
            self.input_amount = f"{self.input_amount:,}"
            self.spend_amount = f"{self.spend_amount:,}"
            self.fee_amount = f"{self.fee_amount:,}"

        longest_amount = max(
            len(self.input_amount),
            len(self.spend_amount),
            len(self.fee_amount),
        )
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
        # TODO: Test rendering the numeric amounts without the supersampling
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
        left, top, right, bottom = fixed_width_font.getbbox(self.input_amount + "+")
        digits_width, digits_height = right - left, bottom - top

        # Draw each line of the equation
        cur_y = 0

        def render_amount(
            cur_y, amount_str, info_text, info_text_color=GUIConstants.BODY_FONT_COLOR
        ):
            secondary_digit_color = "#888"
            tertiary_digit_color = "#666"
            digit_group_spacing = 2 * ssf
            # secondary_digit_color = GUIConstants.BODY_FONT_COLOR
            # tertiary_digit_color = GUIConstants.BODY_FONT_COLOR
            # digit_group_spacing = 0
            if denomination == _("bch"):
                display_str = amount_str
                main_zone = display_str[:-6]
                mid_zone = display_str[-6:-3]
                end_zone = display_str[-3:]
                left, top, right, bottom = fixed_width_font.getbbox(main_zone)
                main_zone_width, th = right - left, bottom - top
                left, top, right, bottom = fixed_width_font.getbbox(end_zone)
                mid_zone_width, th = right - left, bottom - top
                draw.text(
                    (0, cur_y),
                    text=main_zone,
                    font=fixed_width_font,
                    fill=GUIConstants.BODY_FONT_COLOR,
                )
                draw.text(
                    (main_zone_width + digit_group_spacing, cur_y),
                    text=mid_zone,
                    font=fixed_width_font,
                    fill=secondary_digit_color,
                )
                draw.text(
                    (
                        main_zone_width
                        + digit_group_spacing
                        + mid_zone_width
                        + digit_group_spacing,
                        cur_y,
                    ),
                    text=end_zone,
                    font=fixed_width_font,
                    fill=tertiary_digit_color,
                )
            else:
                draw.text(
                    (0, cur_y),
                    text=amount_str,
                    font=fixed_width_font,
                    fill=GUIConstants.BODY_FONT_COLOR,
                )
            draw.text(
                (digits_width + 3 * digit_group_spacing, cur_y),
                text=info_text,
                font=body_font,
                fill=info_text_color,
            )

        render_amount(
            cur_y,
            f" {self.input_amount}",
            info_text=ngettext("input", "inputs", self.num_inputs),
        )

        # spend_amount will be zero on self-transfers; only display when there's an
        # external recipient.
        if self.num_outputs > 0:
            cur_y += digits_height + GUIConstants.BODY_LINE_SPACING * ssf
            render_amount(
                cur_y,
                f"-{self.spend_amount}",
                info_text=ngettext("output", "outputs", self.num_outputs),
            )

        cur_y += digits_height + GUIConstants.BODY_LINE_SPACING
        draw.line((0, cur_y, image.width, cur_y), fill=GUIConstants.BODY_FONT_COLOR, width=1)

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
class PSBTAddressDetailsScreen(PSBTButtonListScreen):
    address: str = None
    amount: int = 0
    button_title: str = _("Next")
    category_id: str = None

    def __post_init__(self):
        # Customize defaults
        self.is_bottom_list = True
        for category in categories:
            if category.category_id == self.category_id:
                self.category: Category = category
                break
        else:
            self.category: Category = Category(
                category_id=self.category_id,
                token_symbol="Unknown",
                decimal=0,
                icon_name=SeedCashIconsConstants.CASHTOKEN,
                icon_color=GUIConstants.ACCENT_COLOR,
            )
        self.button_data = [ButtonOption(self.button_title, button_color=self.category.icon_color)]
        super().__post_init__()

        center_img_height = self.buttons[0].screen_y - self.top_nav.height

        # Figuring out how to vertically center the sats and the address is
        # difficult so we just render to a temp image and paste it in place.
        center_img = Image.new(
            "RGB", (self.canvas_width, center_img_height), GUIConstants.BACKGROUND_COLOR
        )
        draw = ImageDraw.Draw(center_img)

        if self.category_id:
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
            font_accent_color=self.category.icon_color,
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
class PSBTOpReturnScreen(PSBTButtonListScreen):
    op_return_data: bytes = None

    def __post_init__(self):
        # Customize defaults
        self.is_bottom_list = True

        super().__post_init__()

        try:
            # Simple case: display human-readable text
            self.components.append(
                TextArea(
                    text=self.op_return_data.decode(
                        errors="strict"
                    ),  # "strict" is a good enough heuristic to decide if it's human readable
                    font_size=GUIConstants.get_top_nav_title_font_size(),
                    is_text_centered=True,
                    allow_text_overflow=True,
                    screen_y=self.top_nav.height + GUIConstants.COMPONENT_PADDING,
                    height=self.buttons[0].screen_y
                    - self.top_nav.height
                    - 2 * GUIConstants.COMPONENT_PADDING,
                )
            )
            return
        except UnicodeDecodeError:
            # Contains data that can't be converted to UTF-8; probably encoded and not
            # meant to be human readable.
            font = Fonts.get_font(
                GUIConstants.FIXED_WIDTH_FONT_NAME,
                size=GUIConstants.BODY_FONT_SIZE,
            )
            left, top, right, bottom = font.getbbox("X", anchor="ls")
            chars_per_line = int(
                (self.canvas_width - 2 * GUIConstants.EDGE_PADDING) / (right - left)
            )
            decoded_str = self.op_return_data.hex()
            num_lines = math.ceil(len(decoded_str) / chars_per_line)
            text = ""
            for i in range(num_lines):
                text += (
                    decoded_str[i * chars_per_line : (i + 1) * chars_per_line]
                ) + "\n"
            text = text[:-1]

            # TRANSLATOR_NOTE: Shown when displaying OP_RETURN as non-human-readable hexadecimal data
            hex_label = _("raw hex data")
            label = TextArea(
                text=hex_label,
                font_color=GUIConstants.LABEL_FONT_COLOR,
                font_size=GUIConstants.LABEL_FONT_SIZE,
                screen_y=self.top_nav.height,
            )
            self.components.append(label)

            self.components.append(
                TextArea(
                    text=text,
                    font_name=GUIConstants.FIXED_WIDTH_FONT_NAME,
                    font_size=GUIConstants.BODY_FONT_SIZE,
                    screen_y=label.screen_y
                    + label.height
                    + GUIConstants.COMPONENT_PADDING,
                )
            )

@dataclass
class PSBTFinalizeScreen(PSBTButtonListScreen):
    def __post_init__(self):
        # Customize defaults
        self.title = _("Sign PSBT")
        self.is_bottom_list = True
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
                text=_("Click to approve this transaction"),
                screen_y=icon.screen_y
                + icon.height
                + 2 * GUIConstants.COMPONENT_PADDING,
            )
        )

@dataclass
class PSBTNFTScreen(PSBTButtonListScreen):
    category_id: str = None

    def __post_init__(self):
        # Customize defaults
        self.title = _("Review PSBT")
        self.is_bottom_list = True
        self.button_data = [ButtonOption("Next", button_color=GUIConstants.MUSD_BLUE)]
        super().__post_init__()
        
        # collection TODO: For now we have unkown we will add collection in future
        y_offset = self.top_nav.height
        
        self.components.append(
            TextArea(
                text="Collection",
                font_size=GUIConstants.BODY_FONT_SIZE - 4,
                is_text_centered=False,
                screen_y=y_offset,
            )
        )
        y_offset += GUIConstants.BODY_FONT_SIZE
        self.components.append(
            RoundedTextArea(
                text="Unknown",
                font_size=GUIConstants.BODY_FONT_SIZE,
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

        y_offset += GUIConstants.BODY_FONT_SIZE
        self.components.append(
            RoundedTextArea(
                text=self.category_id,
                font_size=GUIConstants.BODY_FONT_SIZE,
                is_text_centered=False,
                treat_chars_as_words=True,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=y_offset,
            )
        )
@dataclass
class PSBTNFTDetailsScreen(PSBTButtonListScreen):
    output_num: int = None
    nft_commitment: str = None
    nft_capability: str = None

    def __post_init__(self):
        # Customize defaults
        self.title = _("Review PSBT")
        self.is_bottom_list = True
        self.button_data = [ButtonOption("Next", button_color=GUIConstants.MUSD_BLUE)]
        super().__post_init__()

        # Type
        y_offset = self.top_nav.height + GUIConstants.COMPONENT_PADDING
        self.components.append(
            TextArea(
                text=f"NFT #{self.output_num}",
                font_size=GUIConstants.BODY_FONT_SIZE,
                screen_y=y_offset,
            )
        )

        y_offset += GUIConstants.BODY_FONT_SIZE
        self.components.append(
            TextArea(
                text="Type",
                font_size=GUIConstants.BODY_FONT_SIZE - 4,
                is_text_centered=False,
                screen_y=y_offset,
            )
        )

        y_offset += GUIConstants.BODY_FONT_SIZE
        self.components.append(
            RoundedTextArea(
                text=self.nft_capability,
                font_size=GUIConstants.BODY_FONT_SIZE,
                is_text_centered=False,
                treat_chars_as_words=True,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=y_offset,
            )
        )

        # Commitment
        y_offset += GUIConstants.BODY_FONT_SIZE + 2 * GUIConstants.COMPONENT_PADDING
        self.components.append(
            TextArea(
                    text="Commitment",
                    font_size=GUIConstants.BODY_FONT_SIZE - 4,
                    is_text_centered=False,
                    screen_y=y_offset,
                )
            )
        y_offset += GUIConstants.BODY_FONT_SIZE
        self.components.append(
            RoundedTextArea(
                text=self.nft_commitment,
                font_size=GUIConstants.BODY_FONT_SIZE,
                is_text_centered=False,
                treat_chars_as_words=True,
                screen_x=GUIConstants.EDGE_PADDING,
                screen_y=y_offset,
            )
        )

@dataclass
class PSBTNFTAddressScreen(PSBTButtonListScreen):
    destination_addr: str = None
    index: int = None

    def __post_init__(self):
        self.title = _("Will Send")
        self.is_bottom_list = True
        self.button_data = [ButtonOption("Next", button_color=GUIConstants.MUSD_BLUE)]
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

