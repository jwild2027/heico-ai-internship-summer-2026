from __future__ import annotations

from tiff.visual_text_extraction import (
    is_probable_vision_model,
    select_ollama_vision_model,
    select_ollama_vision_model_candidates,
)


def test_select_ollama_vision_model_prefers_verified_llava_over_qwen3_vl() -> None:
    models = [
        "bge-m3:latest",
        "llava:13b",
        "qwen3-vl:latest",
        "llama3.1:8b",
    ]

    assert select_ollama_vision_model(models) == "llava:13b"


def test_select_ollama_vision_model_falls_back_to_installed_visionish_name() -> None:
    assert select_ollama_vision_model(["custom-vl-model:latest", "bge-m3:latest"]) == "custom-vl-model:latest"


def test_probable_vision_model_does_not_treat_embedding_models_as_vision() -> None:
    assert is_probable_vision_model("qwen3-vl:latest")
    assert is_probable_vision_model("llava:13b")
    assert not is_probable_vision_model("bge-m3:latest")
    assert not is_probable_vision_model("nomic-embed-text:latest")


def test_select_ollama_vision_model_candidates_keep_qwen_as_fallback() -> None:
    models = [
        "bge-m3:latest",
        "llava:13b",
        "qwen3-vl:latest",
        "llama3.1:8b",
    ]

    assert select_ollama_vision_model_candidates(models)[:2] == ["llava:13b", "qwen3-vl:latest"]
