"""Token transition completeness, navigation and exact transaction displays."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seedcash.models.psbt_parser import Token, TxOutput, TxInput, ScriptType, PSBTParser
from seedcash.models.token_review import TokenReview, InvalidTokenState, format_amount, script_preview, op_return_payload_length
from seedcash.views import psbt_views as views
from seedcash.gui.screens import RET_CODE__BACK_BUTTON

A, B = '11' * 32, '22' * 32

def output(category=A, amount=None, capability=None, commitment='', index=0):
    token = Token(b'', b'', category, amount,
                  Token.NFTData(capability, commitment) if capability else None)
    return TxOutput(500, index=index, token=token, address='recipient')

def parser(inputs=(), outputs=(), genesis=None):
    txins = [TxInput(bytes.fromhex(genesis or '33' * 32)[::-1], 0 if genesis else 1, 0, spent_output=o) for o in inputs]
    if genesis and not txins:
        txins = [TxInput(bytes.fromhex(genesis)[::-1], 0, 0, spent_output=TxOutput(1000))]
    return SimpleNamespace(tx=SimpleNamespace(inputs=txins, outputs=list(outputs)))

@pytest.mark.parametrize('value', [True, '1', 1.5, -1])
def test_malformed_amount_fails_closed(value):
    with pytest.raises(InvalidTokenState):
        TokenReview.from_parser(parser([output(amount=value)]))

def test_none_and_empty_token_sets():
    assert TokenReview.from_parser(parser()).categories == ()
    review = TokenReview.from_parser(parser([output(capability='none')], [output(capability='none')]))
    assert review.categories[0].input_amount == 0
    assert not review.categories[0].burned

def test_mixed_old_and_genesis_categories_and_ft_burn():
    review = TokenReview.from_parser(parser([output(A, 10)], [output(A, 3), output(B, 7)], genesis=B))
    assert [c.category_id for c in review.categories] == [A, B]
    old, new = review.categories
    assert old.burned_amount == 7 and new.minted_amount == 7 and new.genesis
    assert sum(c.genesis for c in review.categories) == 1
    text = ''.join(t.replace('\n', '') for _, t in review.pages())
    assert A in text and B in text

def test_multiple_nfts_mint_burn_and_mutable_commitment():
    review = TokenReview.from_parser(parser(
        [output(capability='minting', commitment='01'), output(capability='none', commitment='02'), output(capability='mutable', commitment='03')],
        [output(capability='minting', commitment='01'), output(capability='minting', commitment='04', index=1), output(capability='none', commitment='05', index=2)]))
    c = review.categories[0]
    assert len(c.inputs) == len(c.outputs) == 3
    assert len(c.modified) == len(c.minted) == len(c.burned) == 1
    assert c.burned[0].commitment == '02'
    assert c.modified[0][0].capability == 'mutable'
    assert c.modified[0][1].capability == 'none'
    titles = [title for title, _ in review.pages()]
    for expected in ('NFT input', 'NFT output', 'NFT minted', 'NFT burned', 'NFT commitment', 'NFT modified'):
        assert expected in titles

@pytest.mark.parametrize('capability,commitment', [('none','02'), ('mutable','01'), ('minting','01')])
def test_immutable_modification_without_authority_rejected(capability, commitment):
    with pytest.raises(InvalidTokenState):
        TokenReview.from_parser(parser([output(capability='none', commitment='01')], [output(capability=capability, commitment=commitment)]))

def test_unknown_category_and_output_only_category_fail_closed():
    with pytest.raises(InvalidTokenState):
        TokenReview.from_parser(parser([], [output(B, 1)]))
    review = TokenReview.from_parser(parser([output(B, 2)], [output(B, 1)]))
    assert review.categories[0].category_id == B

@pytest.mark.parametrize('sats,expected', [(1,'0.00000001'), (12345678,'0.12345678'), (100000000,'1.00000000'), (123456789123456789,'1234567891.23456789')])
def test_exact_bch_format(sats, expected):
    assert format_amount(sats, 8) == expected

def test_full_token_format_and_bounded_binary_preview():
    assert format_amount(1234567890123456789, 9) == '1234567890.123456789'
    data = b'\x00\x1b\xff' * 100000
    size, text = script_preview(data)
    assert size == 300000 and len(text) == 51 and text.endswith('...')
    assert op_return_payload_length(b'\x6a\x03abc') == 3
    assert op_return_payload_length(b'\x6a\x4c\x03abc') == 3
    assert op_return_payload_length(b'\x6a\x4c\xffabc') is None

def view(cls, controller, **attrs):
    instance = cls.__new__(cls)
    instance.controller = controller
    instance.run_screen = Mock(return_value=0)
    for k, v in attrs.items():
        setattr(instance, k, v)
    return instance

def test_every_review_page_back_navigation_and_completion():
    p = parser([output(A, 10)], [output(A, 5)])
    review = TokenReview.from_parser(p)
    ctl = SimpleNamespace(psbt_parser=p, token_review_parser=p, token_review=review, token_review_acknowledged=set())
    for page in range(len(review.pages())):
        instance = view(views.PSBTTokenReviewView, ctl, page=page)
        destination = instance.run()
        assert ctl.token_review_acknowledged == set(range(page + 1))
        assert destination.View_cls is (views.BCHPSBTOverviewView if page + 1 == len(review.pages()) else views.PSBTTokenReviewView)
    for page in reversed(range(len(review.pages()))):
        ctl.token_review_acknowledged = set(range(len(review.pages())))
        instance = view(views.PSBTTokenReviewView, ctl, page=page)
        instance.run_screen.return_value = RET_CODE__BACK_BUTTON
        destination = instance.run()
        assert ctl.token_review_acknowledged == set(range(page))
        assert destination.View_cls is (views.PSBTDiscardWarningView if page == 0 else views.PSBTTokenReviewView)


def test_incomplete_or_changed_review_cannot_reach_signing_screen():
    p = parser([output(A, 10)], [output(A, 5)])
    review = TokenReview.from_parser(p)
    ctl = SimpleNamespace(psbt_parser=p, token_review_parser=p, token_review=review, token_review_acknowledged={0})
    instance = view(views.PSBTConfirmationView, ctl)
    assert instance.run().View_cls is views.PSBTSigningErrorView
    instance.run_screen.assert_not_called()
    ctl.token_review_acknowledged = set(range(len(review.pages())))
    p.tx.outputs[0].token.ft_amount = 4
    assert instance.run().View_cls is views.PSBTSigningErrorView


def test_op_return_first_overview_and_p2pk_satoshis():
    p = PSBTParser.__new__(PSBTParser)
    p.total_input_amount = 11000
    p.total_output_amount = 10000
    p.tx = SimpleNamespace(inputs=[None], outputs=[
        TxOutput(9000, index=0, script_type=ScriptType.OP_RETURN, full_script=b'\x6a\x01a'),
        TxOutput(1000, index=1, script_type=ScriptType.P2PK, full_script=b'\x21' + bytes(33) + b'\xac')])
    ctl = SimpleNamespace(psbt_parser=p)
    instance = view(views.BCHPSBTOverviewView, ctl, is_last=False)
    instance.run()
    assert instance.run_screen.call_args.kwargs['inputs_amount'] == 1000
    instance = view(views.PSBTP2PKView, ctl, output_num=0)
    instance.run()
    assert instance.run_screen.call_args.kwargs['value_satoshis'] == 1000
    instance = view(views.PSBTOpReturnView, ctl, output_num=0)
    assert instance.run().View_cls is views.PSBTP2PKView
    assert instance.run_screen.call_args.kwargs['value_satoshis'] == 9000


def test_math_without_address_outputs_does_not_skip_script_review():
    p = SimpleNamespace(total_input_amount=10, total_output_amount=9, input_count=1, output_count=1,
                        fee_amount=1, bch_outputs=[], has_op_return=True, has_p2pk=False)
    instance = view(views.PSBTMathView, SimpleNamespace(psbt_parser=p))
    assert instance.run().View_cls is views.PSBTOpReturnView


def test_minting_downgrade_and_ft_attachment_are_reviewed_modifications():
    review = TokenReview.from_parser(parser(
        [output(amount=5, capability='minting', commitment='01')],
        [output(amount=3, capability='mutable', commitment='01')]))
    c = review.categories[0]
    assert len(c.modified) == 1 and not c.minted and not c.burned
    assert c.modified[0][0].amount == 5 and c.modified[0][1].amount == 3
    assert c.burned_amount == 2
    review = TokenReview.from_parser(parser([output(amount=5, capability='none')], [output(amount=3, capability='none')]))
    assert len(review.categories[0].modified) == 1


def test_ambiguous_mutable_transition_fails_closed():
    with pytest.raises(InvalidTokenState, match='ambiguous'):
        TokenReview.from_parser(parser([output(capability='mutable')],
                                      [output(capability='none', commitment='01'), output(capability='none', commitment='02')]))


def test_math_screen_keeps_one_satoshi_fee_and_bch_units(monkeypatch):
    from seedcash.gui.screens import psbt_screens as screens
    def setup(self):
        self.canvas_width = 240
        self.top_nav = SimpleNamespace(height=48)
        self.buttons = [SimpleNamespace(screen_y=220)]
        self.paste_images = []
    monkeypatch.setattr(screens.SeedCashButtonListWithNav, '__post_init__', setup)
    screen = screens.PSBTMathScreen.__new__(screens.PSBTMathScreen)
    screen.input_amount = 2100000000000000
    screen.spend_amount = 2099999999999999
    screen.fee_amount = 1
    screen.input_count = screen.output_count = 1
    screen.__post_init__()
    assert screen.fee_amount.strip() == '0.00000001'
    assert screen.input_amount.strip() == '21000000.00000000'
    assert screen.spend_amount.strip() == '20999999.99999999'
    assert screen.paste_images


def test_op_return_screen_never_decodes_control_bytes_and_shows_satoshis(monkeypatch):
    from seedcash.gui.screens import psbt_screens as screens
    captured = []
    def setup(self):
        self.top_nav = SimpleNamespace(height=48)
        self.buttons = [SimpleNamespace(screen_y=220)]
        self.components = []
    monkeypatch.setattr(screens.SeedCashButtonListWithNav, '__post_init__', setup)
    monkeypatch.setattr(screens, 'TextArea', lambda **kwargs: captured.append(kwargs) or kwargs)
    screen = screens.PSBTOpReturnScreen.__new__(screens.PSBTOpReturnScreen)
    screen.title = 'OP_RETURN'
    screen.value_satoshis = 17
    screen.op_return_data = b'\x6a\x03\x00\x1b\xff'
    screen.__post_init__()
    text = captured[0]['text']
    assert '17 satoshis' in text and 'Payload: 3 bytes' in text
    assert '6a03001bff' in text and '\x1b' not in text and '\x00' not in text
