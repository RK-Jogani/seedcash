"""PSBT review contracts using real token models and scripted screen responses.

Screens are intercepted before rendering; no hardware or private keys are used.
Failures describe required behavior rather than preserving known UI defects.
"""
from types import SimpleNamespace

import pytest

from seedcash.models.psbt_parser import Category, Token, TokenReview, TxInput, TxOutput
from seedcash.views import psbt_views as views
from seedcash.views.view import BackStackView, Destination, View
from seedcash.gui.screens import RET_CODE__BACK_BUTTON as BACK


@pytest.mark.parametrize('script,expected', [
    (b'\x6a\x05hello', 'hello'),
    (b'\x6a\x01\xff', 'Unable to decode OP_RETURN data. It may not be valid UTF-8 text.'),
    (b'\x6a\x02x', 'Unable to decode OP_RETURN data. It may not be valid UTF-8 text.'),
])
def test_op_return_review_text(ui, script, expected):
    ui.parser.op_return_outputs = [TxOutput(0, full_script=script)]
    assert views.PSBTOpReturnView().run().View_cls is views.PSBTConfirmationView
    assert ui.calls[-1][1]['text'] == expected


def test_p2pk_review_uses_hex(ui):
    script = b'\x21\x02' + bytes(32) + b'\xac'
    ui.parser.p2pk_outputs = [TxOutput(900, full_script=script)]
    views.PSBTP2PKView().run()
    assert ui.calls[-1][1]['text'] == script.hex()


def test_payload_is_centered_in_inactive_component(monkeypatch):
    from unittest.mock import Mock
    from PIL import Image, ImageDraw
    from seedcash.gui.renderer import Renderer
    from seedcash.gui.components import GUIConstants, RoundedTextArea
    from seedcash.gui.screens.psbt_screens import PSBTCardTextScreen
    from seedcash.gui.screens.screen import ButtonOption
    from seedcash.hardware.buttons import HardwareButtons

    renderer = Renderer.__new__(Renderer)
    renderer.canvas_width = renderer.canvas_height = 240
    renderer.canvas = Image.new('RGB', (240, 240))
    renderer.draw = ImageDraw.Draw(renderer.canvas)
    renderer.disp = Mock()
    monkeypatch.setattr(Renderer, '_instance', renderer)
    monkeypatch.setattr(HardwareButtons, 'get_instance', lambda: Mock())
    screen = PSBTCardTextScreen(
        title='P2PK', text='1234', button_data=[ButtonOption('Next')],
    )
    content = next(c for c in screen.components if isinstance(c, RoundedTextArea))
    assert content.text == '1234'
    assert content.fill_color == GUIConstants.INACTIVE_COLOR
    assert content.is_text_centered
    assert content.text_offset_y > 0
    assert content.screen_y + content.height < screen.canvas_height
    assert not screen.show_check_button
    assert len(screen.buttons) == 1
    assert screen.button_data[0].button_label == 'Next'
    screen._render()
    assert screen.title == 'P2PK'


def category(is_ft=True, genesis=False, amounts=(10, 20), burned=False, minting=False):
    result = Category('11' * 32, is_ft=is_ft, is_genesis=genesis)
    def output(index, amount, capability='none'):
        token = Token(b'', b'', result.category_id,
                      ft_amount=amount if is_ft else None,
                      nft_data=None if is_ft else Token.NFTData(capability, str(index)))
        return TxOutput(546, index=index, token=token, address=f'recipient-{index}')
    result.outputs = [output(i, amount) for i, amount in enumerate(amounts)]
    if not genesis:
        spent = output(0, sum(amounts) + int(burned), 'minting' if minting else 'none')
        result.inputs = [TxInput(bytes(32), 1, 0, spent_output=spent)]
    return result


@pytest.fixture
def ui(monkeypatch):
    parser = SimpleNamespace(token_review=None, outputs=[], input_amount=2000,
                             total_input_amount=2000, total_output_amount=1000,
                             input_count=1, output_count=1, fee_amount=1000,
                             has_op_return=False, has_p2pk=False)
    controller = SimpleNamespace(psbt_parser=parser, psbt_bytes=b'psbt', psbt_seed=object())
    calls, answers = [], []
    monkeypatch.setattr(View, '__init__', lambda self: setattr(self, 'controller', controller))
    def screen(self, cls, **kwargs):
        calls.append((cls.__name__, kwargs))
        return answers.pop(0) if answers else 0
    monkeypatch.setattr(View, 'run_screen', screen)
    metadata = SimpleNamespace(token_symbol='TEST', icon_color='blue')
    monkeypatch.setattr(views, 'get_category', lambda _: metadata)
    def select(cat):
        parser.token_review = TokenReview(ft_categories=[cat] if cat.is_ft else [],
                                         nft_categories=[] if cat.is_ft else [cat])
        parser.token_review.initiate
    return SimpleNamespace(controller=controller, parser=parser, calls=calls,
                           answers=answers, metadata=metadata, select=select)


@pytest.mark.parametrize('ft,nft', [(1,0),(0,1),(1,1),(2,2),(0,3),(3,0)])
def test_category_round_trip(ft, nft):
    categories = [Category(f'ft{i}', is_ft=True) for i in range(ft)]
    categories += [Category(f'nft{i}') for i in range(nft)]
    review = TokenReview(ft_categories=categories[:ft], nft_categories=categories[ft:])
    review.initiate
    assert review.current_category is categories[0]
    for item in categories[1:]:
        assert review.next_category is item
    # Exhaustion must preserve the last category for Back navigation.
    assert review.next_category is None
    assert review.current_category is categories[-1]
    for item in reversed(categories[:-1]):
        assert review.previous_category is item
    assert review.previous_category is None


@pytest.mark.parametrize('is_ft', [True, False])
@pytest.mark.parametrize('answer', [0, BACK])
def test_genesis_warning(ui, is_ft, answer):
    ui.select(category(is_ft, genesis=True))
    ui.answers.append(answer)
    destination = views.GenesisWarningView().run()
    assert ui.calls[0][1]['title'] == 'Genesis Transaction'
    assert ui.calls[0][1]['status_headline'] == ('New Fungible Token' if is_ft else 'New Non-Fungible Token')
    expected = views.PSBTDiscardWarningView if answer == BACK else (
        views.PSBTFungibleTokenWarningsView if is_ft else views.PSBTNonFungibleTokenWarningsView)
    assert destination.View_cls is expected


def test_ft_burn_warning_before_details(ui):
    ui.select(category(burned=True))
    assert views.PSBTFungibleTokenWarningsView().run().View_cls is views.PSBTFungibleTokenDetailsView
    assert [kw['title'] for _, kw in ui.calls] == ['Burning Fungible Token(s)']


def test_unknown_ft_warning_then_category_id(ui):
    ui.select(category())
    ui.metadata.token_symbol = '[?]'
    views.PSBTFungibleTokenWarningsView().run()
    assert [name for name, _ in ui.calls] == ['WarningScreen', 'PSBTNFTScreen']
    assert ui.calls[1][1]['category_id'] == '11' * 32


def test_unknown_ft_back_does_not_repeat_same_warning(ui):
    ui.select(category())
    ui.metadata.token_symbol = '[?]'
    ui.answers.append(BACK)
    destination = views.PSBTFungibleTokenWarningsView().run()
    assert destination.View_cls is views.PSBTDiscardWarningView


def test_nft_minting_and_burn_warning_order(ui):
    ui.select(category(False, minting=True))
    destination = views.PSBTNonFungibleTokenWarningsView().run()
    assert destination.View_cls is views.PSBTNFTDetailsView
    assert [kw['title'] for name, kw in ui.calls if name == 'WarningScreen'] == [
        'Minting Non-Fungible Token(s)', 'Burning Non-Fungible Token(s)']
    assert ui.calls[-1][0] == 'PSBTNFTScreen'
    assert ui.calls[-1][1]['category_id'] == '11' * 32


@pytest.mark.parametrize('is_ft', [True, False])
def test_burn_warning_back_discards_first_category(ui, is_ft):
    ui.select(category(is_ft, burned=True, amounts=()))
    ui.answers.append(BACK)
    cls = views.PSBTFungibleTokenWarningsView if is_ft else views.PSBTNonFungibleTokenWarningsView
    assert cls().run().View_cls is views.PSBTDiscardWarningView


@pytest.mark.parametrize('cls,cursor,is_ft', [
    (views.PSBTFungibleTokenAddressDetailsView, 'output_no', True),
    (views.PSBTNFTDetailsView, 'nft_detail_no', False),
    (views.PSBTNFTAddressDetailsView, 'output_no', False),
])
def test_back_stays_on_previous_item(ui, cls, cursor, is_ft):
    cat = category(is_ft)
    ui.select(cat)
    setattr(cat, cursor, 1)
    ui.answers.append(BACK)
    assert cls().run().View_cls is cls
    assert getattr(cat, cursor) == 0
    ui.answers.append(BACK)
    assert cls().run().View_cls is BackStackView


@pytest.mark.parametrize('is_ft', [True, False])
def test_complete_burn_can_finish_review_without_recipient(ui, is_ft):
    ui.select(category(is_ft, amounts=(), burned=True))
    cls = views.PSBTFungibleTokenWarningsView if is_ft else views.PSBTNonFungibleTokenWarningsView
    destination = cls().run()
    for _ in range(5):
        if destination.View_cls is views.BCHPSBTOverviewView:
            break
        destination = destination.View_cls(**(destination.view_args or {})).run()
    assert destination.View_cls is views.BCHPSBTOverviewView
    assert all(kw.get('address', 'valid') is not None for _, kw in ui.calls)


def test_high_amount_warning_shows_recipient_amount(ui):
    ui.select(category(amounts=(1_000_000_000,)))
    destination = views.PSBTFungibleTokenDetailsView().run()
    assert destination.View_cls is views.PSBTAddressDetailsWarningView
    assert destination.View_cls().run().View_cls is views.PSBTFungibleTokenAddressDetailsView
    assert '1000000000 TEST' in ui.calls[-1][1]['text']


@pytest.mark.parametrize('op_return,p2pk,expected', [
    (True,False,views.PSBTOpReturnView),
    (False,True,views.PSBTP2PKView),
    (False,False,views.PSBTConfirmationView),
])
def test_math_without_address_outputs_routes(ui, op_return, p2pk, expected):
    ui.parser.has_op_return, ui.parser.has_p2pk = op_return, p2pk
    destination = views.PSBTMathView().run()
    assert destination is not None
    assert destination.View_cls is expected


def test_bch_recipient_op_return_p2pk_confirmation(ui):
    ui.parser.outputs = [TxOutput(1000, address='alice')]
    ui.parser.has_op_return = ui.parser.has_p2pk = True
    ui.parser.op_return_outputs = [TxOutput(0, full_script=b'\x6a\x02hi')]
    ui.parser.p2pk_outputs = [TxOutput(0, full_script=b'Q')]
    for cls, expected in [(views.BCHPSBTOverviewView,views.PSBTMathView),
                          (views.PSBTMathView,views.PSBTAddressDetailsView),
                          (views.PSBTAddressDetailsView,views.PSBTOpReturnView),
                          (views.PSBTOpReturnView,views.PSBTP2PKView),
                          (views.PSBTP2PKView,views.PSBTConfirmationView)]:
        assert cls().run().View_cls is expected
    assert ui.calls[2][1]['amount'] == 1000


@pytest.mark.parametrize('failure', [False, True])
def test_signing_routes_and_error_warning(ui, failure):
    def sign(parser):
        assert parser is ui.parser
        if failure:
            raise ValueError('private error')
        return b'signed'
    ui.controller.storage = SimpleNamespace(wallet=SimpleNamespace(sign_psbt=sign))
    destination = views.PSBTConfirmationView().run()
    assert destination.View_cls is (views.PSBTSigningErrorView if failure else views.PSBTSignedQRDisplayView)
    if failure:
        assert views.PSBTSigningErrorView().run().View_cls is views.WalletOptionsView
        assert ui.calls[-1][1]['status_headline'] == 'Signing Failed'
        assert 'private error' not in ui.calls[-1][1]['text']
    else:
        assert ui.controller.psbt_bytes == b'signed'


@pytest.mark.parametrize('answer', [0, BACK])
def test_discard_warning_requires_confirmation(ui, answer):
    discarded = []
    ui.controller.discard_psbt = lambda: discarded.append(True)
    ui.answers.append(answer)
    destination = views.PSBTDiscardWarningView().run()
    assert discarded == ([True] if answer == 0 else [])
    assert destination.View_cls is (views.WalletOptionsView if answer == 0 else BackStackView)


@pytest.mark.parametrize('kind', ['bch', 'ft', 'nft', 'genesis-ft', 'genesis-nft', 'invalid'])
def test_loading_routes_and_stops_animation(ui, monkeypatch, kind):
    from seedcash.gui.screens import screen
    lifecycle = []
    class Loading:
        def __init__(self, **kwargs):
            pass
        def start(self):
            lifecycle.append('start')
        def stop(self):
            lifecycle.append('stop')
    monkeypatch.setattr(screen, 'LoadingScreenThread', Loading)
    monkeypatch.setattr(views.time, 'sleep', lambda _: None)
    if kind not in ('bch', 'invalid'):
        ui.select(category(is_ft=kind.endswith('ft') and not kind.endswith('nft'),
                           genesis=kind.startswith('genesis')))
    def parse(raw):
        assert raw == b'psbt'
        assert ui.controller.psbt_parser is None
        if kind == 'invalid':
            raise ValueError('private parser details')
        return ui.parser
    monkeypatch.setattr(views, 'PSBTParser', parse)
    destination = views.LoadingPSBTView().run()
    expected = {'bch': views.BCHPSBTOverviewView,
                'ft': views.PSBTFungibleTokenWarningsView,
                'nft': views.PSBTNonFungibleTokenWarningsView,
                'genesis-ft': views.GenesisWarningView,
                'genesis-nft': views.GenesisWarningView,
                'invalid': views.PSBTParsingErrorView}[kind]
    assert destination.View_cls is expected
    assert destination.skip_current_view
    assert lifecycle == ['start', 'stop']


def test_recipient_back_with_controller_history(ui):
    from seedcash.controller import Controller
    ui.select(category())
    overview = Destination(views.PSBTFungibleTokenDetailsView)
    recipient = Destination(views.PSBTFungibleTokenAddressDetailsView)
    # Use the controller's destination equality and real Back pop behavior.
    recipient.view_args = {}
    history = [overview, recipient]
    destination = views.PSBTFungibleTokenAddressDetailsView().run()
    destination.view_args = {}
    if history[-1] != destination:
        history.append(destination)
    ui.answers.append(BACK)
    destination = destination.View_cls().run()
    if destination.View_cls is BackStackView:
        destination = Controller.pop_prev_from_back_stack(SimpleNamespace(back_stack=history))
    assert destination.View_cls is views.PSBTFungibleTokenAddressDetailsView
    assert ui.parser.token_review.current_category.output_no == 0


def test_high_amount_warning_for_later_recipient(ui):
    ui.select(category(amounts=(1, 1_000_000_000)))
    destination = views.PSBTFungibleTokenDetailsView().run()
    assert destination.View_cls is views.PSBTFungibleTokenAddressDetailsView
    destination = destination.View_cls().run()
    assert destination.View_cls is views.PSBTAddressDetailsWarningView
