from pathlib import Path

from tiff.pipeline_runner import (
    PipelineConfig,
    build_pipeline_steps,
    config_from_file,
    format_command,
    read_simple_yaml,
    run_pipeline,
)


def test_read_simple_yaml_flat_values(tmp_path):
    path = tmp_path / "local_config.yaml"
    path.write_text(
        "\n".join(
            [
                "# local test config",
                "db_path: local_data/db/custom.db",
                "embed_model: bge-m3:latest",
                "rescarta_export_dir: local_data/rescarta_exports",
                "quoted: 'hello world'",
            ]
        ),
        encoding="utf-8",
    )

    values = read_simple_yaml(path)

    assert values["db_path"] == "local_data/db/custom.db"
    assert values["embed_model"] == "bge-m3:latest"
    assert values["quoted"] == "hello world"


def test_config_from_file_uses_defaults_and_overrides(tmp_path):
    path = tmp_path / "local_config.yaml"
    path.write_text("db_path: local_data/db/custom.db\nembedding_model: mxbai-embed-large:latest\n", encoding="utf-8")

    config = config_from_file(path)

    assert config.db_path == "local_data/db/custom.db"
    assert config.embed_model == "mxbai-embed-large:latest"
    assert config.rescarta_export_dir == "local_data/rescarta_exports"
    assert config.config_path == str(path)


def test_build_pipeline_steps_default_contains_expected_order(tmp_path):
    config_path = tmp_path / "local_config.yaml"
    config_path.write_text("db_path: local_data/db/tiff_search.db\nembed_model: bge-m3:latest\n", encoding="utf-8")
    config = PipelineConfig(config_path=str(config_path), questions_path=str(tmp_path / "questions.json"))

    steps = build_pipeline_steps(config)
    names = [step.name for step in steps]

    assert names[:4] == ["search_index", "part_catalog", "rag_chunks", "rag_embeddings"]
    assert "part_catalog_qa" in names
    assert "write_default_eval_questions" in names
    assert names[-1] == "rag_eval"


def test_build_pipeline_steps_honors_skips(tmp_path):
    config = PipelineConfig(
        config_path=str(tmp_path / "missing.yaml"),
        questions_path=str(tmp_path / "questions.json"),
        skip_search_index=True,
        skip_embeddings=True,
        skip_qa=True,
        skip_eval=True,
    )

    names = [step.name for step in build_pipeline_steps(config)]

    assert names == ["part_catalog", "rag_chunks"]


def test_run_pipeline_dry_run_does_not_execute():
    config = PipelineConfig(skip_qa=True, skip_eval=True, skip_embeddings=True)

    results = run_pipeline(config, dry_run=True)

    assert results
    assert all(result.skipped for result in results)
    assert all(result.returncode == 0 for result in results)


def test_format_command_quotes_spaces():
    command = ("python", "script.py", "hello world")

    assert format_command(command) == 'python script.py "hello world"'
