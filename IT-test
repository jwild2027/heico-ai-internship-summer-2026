import argparse
import re
from typing import Any

from ollama import chat


IT_POLICIES = """IT policy reference:

1. Remote Access Encryption Policy
All employees accessing company systems remotely must use AES-512 encrypted VPN tunnels with biometric multi-factor authentication. Sessions inactive for more than 90 seconds are automatically terminated and logged for review.

2. AI Prompt Retention Policy
All prompts submitted to internal AI systems must be retained for 18 months in a centralized audit database. Prompts containing financial forecasts must be tagged with classification level “Predictive-Restricted.”
All prompts containing financial forecasts must be tagged with classification level "Predictive-Restricted."
3. Shadow IT Detection Policy
Any unauthorized SaaS application detected on the corporate network for more than 15 minutes will trigger automatic endpoint isolation and manager notification within one business hour.

4. Quantum-Resistant Credential Policy
All privileged administrator credentials must be rotated every 21 days using post-quantum cryptographic hashing standards approved by the Internal Cryptography Review Board.

5. Portable Device Data Handling Policy
USB storage devices may only be connected to company systems if they are registered, hardware-encrypted, and scanned by the Endpoint Integrity Gateway before mounting.

6. Synthetic Data Usage Policy
Machine learning teams must use datasets containing at least 40% synthetic records when training customer-facing AI systems to reduce exposure of regulated personal information.

7. Emergency Patch Deployment Policy
Critical CVSS 9.0+ vulnerabilities must be patched across internet-facing infrastructure within four hours of vendor disclosure, regardless of maintenance windows.

8. Internal Chat Monitoring Policy
Corporate messaging platforms are subject to automated keyword monitoring for source code leaks, credential sharing, and unauthorized disclosure of merger-related information.

9. Green Computing Compliance Policy
All data center workloads exceeding 70% sustained CPU utilization for more than 48 hours must be evaluated for carbon-efficiency optimization or migration to lower-emission regions.

10. Autonomous Agent Approval Policy
AI agents capable of executing external API calls or modifying production data must receive approval from both the Security Governance Team and the Responsible Automation Committee before deployment.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat with Gemma about IT policies and general IT questions.")
    parser.add_argument("--verbose", action="store_true", help="Print response timing and token metadata.")
    parser.add_argument("--model", default="gemma3:12b", help="Ollama model to use (default: gemma3:12b)")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature (default 0.2)")
    parser.add_argument("--top-p", type=float, default=0.85, help="Top-p nucleus sampling (default 0.85)")
    parser.add_argument("--top-k", type=int, default=30, help="Top-k sampling (default 30)")
    return parser.parse_args()


def print_verbose_metadata(chunk: object) -> None:
    duration_fields = {
        "total_duration",
        "load_duration",
        "prompt_eval_duration",
        "eval_duration",
    }
    count_fields = {
        "prompt_eval_count",
        "eval_count",
    }

    for field in (
        "model",
        "created_at",
        "done",
        "done_reason",
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "prompt_eval_duration",
        "eval_count",
        "eval_duration",
    ):
        value = getattr(chunk, field, None)
        if value is None:
            continue

        if field in duration_fields:
            milliseconds = value / 1_000_000
            print(f"{field}: {value} ns ({milliseconds:.2f} ms)")
        elif field in count_fields:
            print(f"{field}: {value} tokens")
        else:
            print(f"{field}: {value}")


def build_system_prompt() -> str:
    # Strict instructions: answer ONLY using the provided policies,
    # do not infer or assume unstated rules.
    instructions = (
        "You are an IT policy assistant. Answer ONLY using the explicitly provided policies below.\n"
        "If the policies do not specify the requested information, reply exactly: \"The provided policies do not specify this.\"\n"
        "Do not infer, assume, or invent rules that are not present in the policies.\n\n"
        "RESPONSE FORMAT (required):\n"
        "Policy: <Policy Name>\n"
        "Clause: \"<quote the exact clause text>\"\n"
        "Answer: <Direct answer to the user question using only the quoted clause>\n"
        "If the policies do not support an answer, use: The provided policies do not specify this.\n\n"
    )

    return instructions + IT_POLICIES


# Conservative keyword set: model is allowed to pick a policy only when the
# user explicitly references policy-related terms. This helps avoid
# over-eager matches on greetings or generic chit-chat.
POLICY_KEYWORDS = {
    "policy",
    "retention",
    "prompt",
    "remote",
    "vpn",
    "encryption",
    "shadow",
    "saas",
    "credential",
    "usb",
    "portable",
    "synthetic",
    "patch",
    "cvss",
    "monitor",
    "carbon",
    "agent",
    "autonomous",
    "mfa",
    "biometric",
    "rotation",
    "password",
    "admin",
    "vulnerability",
    "session",
    "timeout",
    "approval",
    "cpu",
    "utilization",
    "forecast",
}



GREETING_RE = re.compile(r"^\s*(hi|hello|hey|good morning|good afternoon|good evening|greetings)\b[!., ]*$", re.IGNORECASE)
def policy_intent_score(text):
    text = text.lower()
    return sum(1 for kw in POLICY_KEYWORDS if kw in text)
    # Note: this helper returns how many POLICY_KEYWORDS appear in the text.
    # It does not itself perform greeting checks or reply behavior;
    # the main loop handles those pre-checks.

def main() -> None:
    args = parse_args()
    system_prompt = build_system_prompt()
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    print(f"Using model: {args.model}")
    if args.temperature != 0.2 or args.top_p != 0.85 or args.top_k != 30:
        print(
            "Warning: the active Ollama client does not accept explicit sampling parameters; provided\n"
            "temperature/top_p/top_k values will not be applied to the model call.\n"
            "Behavior can be approximated by system-prompt instructions if you need stricter control."
        )

    while True:
        try:
            user_input = input("IT-test: ")
        except EOFError:
            break
        if user_input.lower() == "exit":
            break

        response_content = ""
        last_chunk = None

        # Quick pre-checks to avoid over-eager policy retrieval on greetings or
        # generic chit-chat. If the input is unrelated to policy topics, reply
        # with the canonical unsupported line and do not call the model.
        if GREETING_RE.match(user_input.strip()):
            reply = "The provided policies do not specify this."
            print(reply)
            messages.append({"role": "user", "content": user_input})
            messages.append({"role": "assistant", "content": reply})
            continue

        lowered = user_input.lower()
        if not any(k in lowered for k in POLICY_KEYWORDS):
            reply = "The provided policies do not specify this."
            print(reply)
            messages.append({"role": "user", "content": user_input})
            messages.append({"role": "assistant", "content": reply})
            continue

        # Call the model with the chosen decoding parameters.
        for chunk in chat(
            model=args.model,
            messages=messages + [{"role": "user", "content": user_input}],
            stream=True,
        ):
            last_chunk = chunk
            if getattr(chunk, "message", None) and getattr(chunk.message, "content", None):
                response_chunk = chunk.message.content
                print(response_chunk, end="", flush=True)
                response_content += response_chunk

        # Append the exchange to the persistent history.
        messages.append({"role": "user", "content": user_input})
        messages.append({"role": "assistant", "content": response_content})
        print("\n")

        if args.verbose and last_chunk is not None:
            print_verbose_metadata(last_chunk)
            print()


if __name__ == "__main__":
    main()
