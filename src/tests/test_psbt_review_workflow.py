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
        views.PSBTFungibleTokenDetailsView if is_ft else views.PSBTTokenDetailsView)
    assert destination.View_cls is expected


def test_unknown_ft_warning_then_category_id(ui):
    ui.select(category())
    ui.metadata.token_symbol = '[?]'
    destination = views.PSBTFTUnknownWarningView().run()
    assert destination.View_cls is views.PSBTTokenDetailsView
    destination.View_cls().run()
    assert [name for name, _ in ui.calls] == ['WarningScreen', 'PSBTNFTScreen']
    assert ui.calls[1][1]['category_id'] == '11' * 32


def test_unknown_ft_back_does_not_repeat_same_warning(ui):
    ui.select(category())
    ui.metadata.token_symbol = '[?]'
    ui.answers.append(BACK)
    destination = views.PSBTFTUnknownWarningView().run()
    assert destination.View_cls is views.PSBTDiscardWarningView


def test_nft_minting_warning(ui):
    ui.select(category(False, minting=True))
    destination = views.PSBTMintingNFTWarningView().run()
    assert destination.View_cls is views.PSBTTokenDetailsView
    assert destination.View_cls().run().View_cls is views.PSBTNFTDetailsView
    assert [kw['title'] for name, kw in ui.calls if name == 'WarningScreen'] == [
        'Minting Non-Fungible Token(s)']
    assert ui.calls[-1][0] == 'PSBTNFTScreen'
    assert ui.calls[-1][1]['category_id'] == '11' * 32


@pytest.mark.parametrize('cls,cursor,is_ft', [
    (views.PSBTFungibleTokenAddressDetailsView, 'output_no', True),
    (views.PSBTNFTDetailsView, 'nft_detail_no', False),
    (views.PSBTNFTAddressDetailsView, 'output_no', False),
])
def test_output_back_uses_saved_history(ui, cls, cursor, is_ft):
    ui.select(category(is_ft))
    ui.answers.append(BACK)
    assert cls(output_num=1).run().View_cls is BackStackView
    # Re-instantiating the saved destination restores the displayed output.
    cls(output_num=0)
    assert getattr(ui.parser.token_review.current_category, cursor) == 0


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
                'ft': views.PSBTFungibleTokenDetailsView,
                'nft': views.PSBTTokenDetailsView,
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
    if history[-1] != destination:
        history.append(destination)
    ui.answers.append(BACK)
    destination = destination.View_cls(**(destination.view_args or {})).run()
    if destination.View_cls is BackStackView:
        destination = Controller.pop_prev_from_back_stack(SimpleNamespace(back_stack=history))
    assert destination.View_cls is views.PSBTFungibleTokenAddressDetailsView
    destination.View_cls(**(destination.view_args or {}))
    assert ui.parser.token_review.current_category.output_no == 0


def test_high_amount_warning_for_later_recipient(ui):
    ui.select(category(amounts=(1, 1_000_000_000)))
    destination = views.PSBTFungibleTokenDetailsView().run()
    assert destination.View_cls is views.PSBTFungibleTokenAddressDetailsView
    destination = destination.View_cls().run()
    assert destination.View_cls is views.PSBTAddressDetailsWarningView


@pytest.mark.parametrize('inputs,outputs,burned', [
    ([('none', 'a')], [], True),
    ([('mutable', 'a')], [('none', 'b')], False),
    ([('none', 'a'), ('none', 'a')], [('none', 'a')], True),
    ([('minting', 'm'), ('none', 'a')], [('minting', 'm'), ('none', 'b')], True),
    ([('minting', 'm'), ('none', 'a'), ('none', 'a')],
     [('minting', 'm'), ('none', 'a'), ('none', 'b')], True),
    ([('minting', 'm')], [('none', 'm')], True),
    ([('minting', 'm')], [('minting', 'changed')], True),
    ([('minting', 'm'), ('none', 'a')],
     [('none', 'new'), ('none', 'a'), ('minting', 'm')], False),
    ([], [('minting', 'genesis')], False),
])
def test_parser_rejects_nft_loss(inputs, outputs, burned):
    from seedcash.models.psbt_parser import PSBTParser
    def output(nft):
        return TxOutput(546, token=Token(b'', b'', 'cat', nft_data=Token.NFTData(*nft)))
    cat = Category('cat', inputs=[TxInput(bytes(32), 1, 0, spent_output=output(nft)) for nft in inputs],
                   outputs=[output(nft) for nft in outputs])
    parser = PSBTParser.__new__(PSBTParser)
    parser.token_review = TokenReview(nft_categories=[cat])
    if burned:
        with pytest.raises(ValueError, match='burns non-fungible'):
            parser.validate_no_token_burning()
    else:
        parser.validate_no_token_burning()


def test_ft_burn_is_rejected_before_nft_validation():
    from seedcash.models.psbt_parser import PSBTParser
    parser = PSBTParser.__new__(PSBTParser)
    parser.token_review = TokenReview(ft_categories=[category(burned=True)], nft_categories=[None])
    with pytest.raises(ValueError, match='burns fungible'):
        parser.validate_no_token_burning()


@pytest.mark.parametrize('fixture_id', ['M06', 'M07'])
def test_burn_psbt_routes_to_invalid_after_loading(ui, monkeypatch, fixture_id):
    import json
    from pathlib import Path
    from seedcash.gui.screens import screen
    fixture = json.loads(Path(__file__).with_name('psbtV145CashTokenScenarios.json').read_text())
    item = next(item for item in fixture['materializedFixtures'] if item['id'] == fixture_id)
    ui.controller.psbt_bytes = bytes.fromhex(item['psbtHex'])
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
    destination = views.LoadingPSBTView().run()
    assert destination.View_cls is views.PSBTParsingErrorView
    assert destination.skip_current_view
    assert ui.controller.psbt_parser is None
    assert lifecycle == ['start', 'stop']
    assert ui.calls == []


@pytest.mark.parametrize('is_ft,unknown,minting,amount,expected', [
    (True, False, False, 10, views.PSBTFungibleTokenDetailsView),
    (True, True, False, 10, views.PSBTFTUnknownWarningView),
    (True, False, False, 10_000_000, views.PSBTFTHighRawAmountWarningsView),
    (False, False, False, 10, views.PSBTTokenDetailsView),
    (False, False, True, 10, views.PSBTMintingNFTWarningView),
])
def test_separate_category_entry_views_and_back(ui, is_ft, unknown, minting, amount, expected):
    cat = category(is_ft, amounts=(amount,), minting=minting)
    ui.select(cat)
    if unknown:
        ui.metadata.token_symbol = '[?]'
    assert views.PSBTTokenView().category_start_view() is expected
    ui.answers.append(BACK)
    assert expected().run().View_cls is views.PSBTDiscardWarningView


def test_unknown_high_amount_ft_uses_separate_views(ui):
    ui.select(category(amounts=(10_000_000,)))
    ui.metadata.token_symbol = '[?]'
    destination = views.PSBTFTUnknownWarningView().run()
    assert destination.View_cls is views.PSBTTokenDetailsView
    destination = destination.View_cls().run()
    assert ui.calls[-1][1]['is_ft'] is True
    assert destination.View_cls is views.PSBTFTHighRawAmountWarningsView
    assert destination.View_cls().run().View_cls is views.PSBTFungibleTokenDetailsView
    ui.answers.append(BACK)
    assert views.PSBTFTHighRawAmountWarningsView().run().View_cls is BackStackView
    assert ui.parser.token_review.current_category is not None


def test_category_transition_and_back_restores_previous_category(ui):
    ft = category(amounts=(10,))
    nft = category(False, amounts=(10,), minting=True)
    review = TokenReview(ft_categories=[ft], nft_categories=[nft])
    ui.parser.token_review = review
    review.initiate
    destination = views.PSBTFungibleTokenAddressDetailsView().run()
    assert destination.View_cls is views.PSBTMintingNFTWarningView
    assert review.current_category is nft
    ui.answers.append(BACK)
    assert destination.View_cls().run().View_cls is BackStackView
    assert review.current_category is ft
    views.PSBTTokenView().next_category()
    destination = views.PSBTNFTAddressDetailsView().run()
    assert destination.View_cls is views.BCHPSBTOverviewView
    assert review.current_category is nft


class ReviewDriver:
    """Run real views and the controller's history rules with scripted buttons."""

    def __init__(self, ui, start):
        self.ui = ui
        self.current = start
        self.history = [start]

    def step(self, answer=0):
        from seedcash.controller import Controller
        self.current.view_args = self.current.view_args or {}
        view = self.current.View_cls(**self.current.view_args)
        category_id = (view.category.category_id if isinstance(view, views.PSBTTokenView) else None)
        self.ui.answers.append(answer)
        before = len(self.ui.calls)
        destination = view.run()
        assert len(self.ui.calls) == before + 1, type(view).__name__
        screen = (type(view), category_id, self.ui.calls[-1])
        assert destination is not None, screen
        if destination.skip_current_view:
            self.history.pop()
        clear_history = destination.clear_history
        if destination.View_cls is BackStackView:
            destination = Controller.pop_prev_from_back_stack(SimpleNamespace(back_stack=self.history))
        if clear_history:
            self.history.clear()
        if not self.history or self.history[-1] != destination:
            self.history.append(destination)
        self.current = destination
        return screen


def make_mixed_review(ui, monkeypatch):
    # Include repeated FT/NFT category IDs: both token types must be reviewed.
    specs = [
        (True, False, False, False, (1, 2, 3)),
        (True, True, False, False, (1, 1_000_000_000, 2)),
        (True, False, False, False, (10_000_000, 2)),
        (True, True, True, False, (1, 2)),
        (False, False, False, False, (1, 2, 3)),
        (False, False, False, True, (1, 2)),
        (False, False, True, False, (1, 2)),
    ]
    categories, metadata = [], {}
    for i, (ft, unknown, genesis, minting, amounts) in enumerate(specs):
        cat = category(ft, genesis=genesis, minting=minting, amounts=amounts)
        cat.category_id = str(i if ft else i - 4)
        metadata.setdefault(cat.category_id, SimpleNamespace(token_symbol='[?]' if unknown else 'TEST', icon_color='blue'))
        for j, out in enumerate(cat.outputs):
            out.address = f'{i}-recipient-{j}'
            if out.token.nft_data:
                out.token.nft_data.commitment = f'{i}-commitment-{j}'
        categories.append(cat)
    monkeypatch.setattr(views, 'get_category', lambda cid: metadata[cid])
    review = TokenReview(ft_categories=categories[:4], nft_categories=categories[4:])
    ui.parser.token_review = review
    review.initiate
    ui.parser.outputs = [TxOutput(1000 + i, address=f'bch-{i}') for i in range(3)]
    ui.parser.has_op_return = ui.parser.has_p2pk = True
    ui.parser.op_return_outputs = [TxOutput(0, full_script=b'\x6a\x01' + bytes([97+i])) for i in range(2)]
    ui.parser.p2pk_outputs = [TxOutput(0, full_script=bytes([i+1])) for i in range(2)]
    return categories


def test_every_category_and_output_reviewed_with_back_at_every_transition(ui, monkeypatch):
    categories = make_mixed_review(ui, monkeypatch)
    driver = ReviewDriver(ui, Destination(views.PSBTTokenView().category_start_view()))
    visited = []
    for _ in range(150):
        if driver.current.View_cls is views.PSBTConfirmationView:
            break
        original = driver.step()
        visited.append(original)
        # Undo every Next, including category boundaries and warning screens.
        driver.step(BACK)
        repeated = driver.step()
        assert repeated == original
    else:
        pytest.fail('Review did not reach confirmation')
    ft_addresses = [kw['address'] for cls, _, (_, kw) in visited
                    if cls is views.PSBTFungibleTokenAddressDetailsView]
    nft_addresses = [kw['destination_addr'] for cls, _, (_, kw) in visited
                     if cls is views.PSBTNFTAddressDetailsView]
    commitments = [kw['nft_commitment'] for cls, _, (_, kw) in visited
                   if cls is views.PSBTNFTDetailsView]
    assert ft_addresses == [out.address for cat in categories if cat.is_ft for out in cat.outputs]
    assert nft_addresses == [out.address for cat in categories if not cat.is_ft for out in cat.outputs]
    assert commitments == [out.token.nft_data.commitment for cat in categories if not cat.is_ft for out in cat.outputs]
    assert [kw['address'] for cls, _, (_, kw) in visited if cls is views.PSBTAddressDetailsView] == ['bch-0', 'bch-1', 'bch-2']
    assert [kw['text'] for cls, _, (_, kw) in visited if cls is views.PSBTOpReturnView] == ['a', 'b']
    assert [kw['text'] for cls, _, (_, kw) in visited if cls is views.PSBTP2PKView] == ['01', '02']
    warnings = [kw['title'] for _, _, (screen, kw) in visited if screen == 'WarningScreen']
    assert warnings.count('Genesis Transaction') == 2
    assert warnings.count('Unknown FT token ID') == 2
    assert warnings.count('Minting Non-Fungible Token(s)') == 1
    assert warnings.count('High Raw Amount') == 3


def test_full_rewind_and_replay_preserves_every_screen(ui, monkeypatch):
    make_mixed_review(ui, monkeypatch)
    driver = ReviewDriver(ui, Destination(views.PSBTTokenView().category_start_view()))
    forward = []
    for _ in range(150):
        if driver.current.View_cls is views.PSBTConfirmationView:
            break
        forward.append(driver.step())
    else:
        pytest.fail('Forward review did not finish')
    driver.step(BACK)  # Leave confirmation without signing.
    for expected in reversed(forward):
        assert driver.step(BACK) == expected
    assert driver.current.View_cls is views.PSBTDiscardWarningView
    driver.step(BACK)  # Cancel discard and resume the first category.
    for expected in forward:
        assert driver.step() == expected
    assert driver.current.View_cls is views.PSBTConfirmationView


@pytest.mark.parametrize('unknown', [False, True])
@pytest.mark.parametrize('amount,warning', [(9_999_999, False), (10_000_000, True)])
def test_ft_total_warning_boundary(ui, unknown, amount, warning):
    ui.select(category(amounts=(amount,)))
    ui.metadata.token_symbol = '[?]' if unknown else 'TEST'
    driver = ReviewDriver(ui, Destination(views.PSBTTokenView().category_start_view()))
    visited = []
    for _ in range(5):
        if driver.current.View_cls is views.PSBTFungibleTokenDetailsView:
            break
        visited.append(driver.step()[0])
    assert driver.current.View_cls is views.PSBTFungibleTokenDetailsView
    assert (views.PSBTFTHighRawAmountWarningsView in visited) is warning
    assert (views.PSBTFTUnknownWarningView in visited) is unknown
    assert (views.PSBTTokenDetailsView in visited) is unknown


@pytest.mark.parametrize('amount,expected', [
    (999_999_999, views.PSBTFungibleTokenAddressDetailsView),
    (1_000_000_000, views.PSBTAddressDetailsWarningView),
])
def test_each_ft_recipient_warning_boundary(ui, amount, expected):
    ui.select(category(amounts=(1, amount, 2)))
    driver = ReviewDriver(ui, Destination(views.PSBTFungibleTokenDetailsView))
    driver.step()
    driver.step()
    assert driver.current.View_cls is expected
    assert driver.current.view_args == {'output_num': 1}
    driver.step(BACK)
    _, _, (_, kw) = driver.step()
    assert kw['address'] == 'recipient-0'
    assert driver.current.View_cls is expected


def test_real_psbt_fixtures_review_all_token_and_bch_outputs(ui):
    import json
    from pathlib import Path
    from seedcash.models.psbt_parser import PSBTParser
    fixture = json.loads(Path(__file__).with_name('psbtV145CashTokenScenarios.json').read_text())
    for item in fixture['materializedFixtures']:
        if item['id'] in ('M06', 'M07'):
            continue  # Burn fixtures are covered by loading rejection tests.
        parser = PSBTParser(bytes.fromhex(item['psbtHex']))
        ui.controller.psbt_parser = parser
        review = parser.token_review
        if review:
            review.initiate
            start = Destination(views.PSBTTokenView().category_start_view())
        else:
            start = Destination(views.BCHPSBTOverviewView, view_args={'is_last': True})
        driver = ReviewDriver(ui, start)
        visited = []
        for _ in range(200):
            if driver.current.View_cls is views.PSBTConfirmationView:
                break
            visited.append(driver.step())
        else:
            pytest.fail(f"{item['id']}: review did not finish")
        ft = review.ft_categories if review else []
        nft = review.nft_categories if review else []
        assert [(cid, kw['address'], kw['amount']) for cls, cid, (_, kw) in visited
                if cls is views.PSBTFungibleTokenAddressDetailsView] == [
                    (cat.category_id, out.address, out.token.ft_amount) for cat in ft for out in cat.outputs
                ], item['id']
        assert [(cid, kw['destination_addr']) for cls, cid, (_, kw) in visited
                if cls is views.PSBTNFTAddressDetailsView] == [
                    (cat.category_id, out.address) for cat in nft for out in cat.outputs
                ], item['id']
        assert [(cid, kw['nft_commitment'], kw['nft_capability']) for cls, cid, (_, kw) in visited
                if cls is views.PSBTNFTDetailsView] == [
                    (cat.category_id, out.token.nft_data.commitment, out.token.nft_data.capability)
                    for cat in nft for out in cat.outputs
                ], item['id']
        assert [(kw['address'], kw['amount']) for cls, _, (_, kw) in visited
                if cls is views.PSBTAddressDetailsView] == [
                    (out.address, out.value_satoshis) for out in parser.outputs
                ], item['id']
