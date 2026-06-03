from tiff.trace_net_ask import build_arg_parser


def test_parser_accepts_query():
    args = build_arg_parser().parse_args(["--query", "seat bottom", "--top-k", "5"])
    assert args.query == "seat bottom"
    assert args.top_k == 5


def test_parser_accepts_page_id():
    args = build_arg_parser().parse_args(["--page-id", "t_p_120_1176_p000010"])
    assert args.page_id == "t_p_120_1176_p000010"


def test_parser_accepts_feedback_simulate():
    args = build_arg_parser().parse_args(["--query", "seat bottom", "--feedback-mode", "simulate"])
    assert args.feedback_mode == "simulate"
