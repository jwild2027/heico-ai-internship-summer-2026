from tiff.visual_text_extraction import parse_args


def test_visual_text_v2_2_is_valid_prompt_version() -> None:
    args = parse_args(["--prompt-version", "visual_text_v2_2"])
    assert args.prompt_version == "visual_text_v2_2"


def test_v2_2_alias_is_valid_prompt_version() -> None:
    args = parse_args(["--prompt-version", "v2_2"])
    assert args.prompt_version == "v2_2"
