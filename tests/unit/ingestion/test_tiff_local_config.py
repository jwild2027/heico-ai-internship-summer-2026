from pathlib import Path

from tiff.local_config import bool_from_config, load_local_config, parse_simple_config_text


def test_parse_simple_config_text_scalars():
    cfg = parse_simple_config_text(
        """
        db_path: local_data/db/tiff_search.db
        llm_model: gemma3:12B
        top_k: 8
        use_llm: true
        use_embeddings: false
        # comment
        """
    )
    assert cfg["db_path"] == "local_data/db/tiff_search.db"
    assert cfg["llm_model"] == "gemma3:12B"
    assert cfg["top_k"] == 8
    assert cfg["use_llm"] is True
    assert cfg["use_embeddings"] is False


def test_load_local_config_merges_defaults(tmp_path: Path):
    path = tmp_path / "local_config.yaml"
    path.write_text("llm_model: gemma3:12B\ntop_k: 12\n", encoding="utf-8")
    cfg = load_local_config(path)
    assert cfg["db_path"] == "local_data/db/tiff_search.db"
    assert cfg["llm_model"] == "gemma3:12B"
    assert cfg["top_k"] == 12
    assert bool_from_config("yes") is True
    assert bool_from_config("no", default=True) is False
