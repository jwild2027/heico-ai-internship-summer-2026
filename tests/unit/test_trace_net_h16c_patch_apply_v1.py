from pathlib import Path
import subprocess
import sys


def test_h16c_apply_patches_return_guard_in_ollama_helper(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "import json\n\n"
        "def call_ollama(url, model, prompt):\n"
        "    payload = {\n"
        "        'model': model,\n"
        "        'prompt': prompt,\n"
        "        'stream': False,\n"
        "    }\n"
        "    data = {'response': 'x'}\n"
        "    response_text = (data.get('response') or '').strip()\n"
        "    if not response_text:\n"
        "        raise RuntimeError('Ollama response did not contain answer text')\n"
        "    return response_text\n",
        encoding="utf-8",
    )
    script = Path("scripts/apply_trace_net_h16c_incomplete_retry_patch_v1.py")
    result = subprocess.run(
        [sys.executable, str(script), "--target", str(target)],
        text=True,
        capture_output=True,
        check=True,
    )
    text = target.read_text(encoding="utf-8")
    assert "quality_status=PASS" in result.stdout
    assert "_h16c_merge_ollama_options(payload)" in text
    assert "Ollama response looked incomplete or truncated" in text
    assert "H16C_INCOMPLETE_ANSWER_RETURN_GUARD_V1" in text


def test_h16c_apply_is_idempotent(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "import json\n\n"
        "def ollama_generate():\n"
        "    payload = {\n"
        "        \"model\": \"m\",\n"
        "        \"prompt\": \"p\",\n"
        "        \"stream\": False,\n"
        "    }\n"
        "    answer_text = 'Answer Evidence Engineering confidence Limits ok enough text ' * 10\n"
        "    return answer_text\n",
        encoding="utf-8",
    )
    script = Path("scripts/apply_trace_net_h16c_incomplete_retry_patch_v1.py")
    subprocess.run([sys.executable, str(script), "--target", str(target)], check=True)
    once = target.read_text(encoding="utf-8")
    subprocess.run([sys.executable, str(script), "--target", str(target)], check=True)
    twice = target.read_text(encoding="utf-8")
    assert once == twice
