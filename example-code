import argparse

from ollama import chat


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat with Ollama using streaming responses.")
    parser.add_argument("--verbose", action="store_true", help="Print response timing and token metadata.")
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

# Initialize an empty message history
messages = []
args = parse_args()

while True:
    user_input = input('Chat with history: ')
    if user_input.lower() == 'exit':
        break
    # Get streaming response while maintaining conversation history
    response_content = ""
    last_chunk = None
    for chunk in chat(
        'gemma3:4b',
        messages=messages + [
            {'role': 'system', 'content': 'You are a helpful assistant. You only give a short sentence by answer.'},
            {'role': 'user', 'content': user_input},
        ],
        stream=True
    ):
        last_chunk = chunk
        if chunk.message:
            response_chunk = chunk.message.content
            print(response_chunk, end='', flush=True)
            response_content += response_chunk
    # Add the exchange to the conversation history
    messages += [
        {'role': 'user', 'content': user_input},
        {'role': 'assistant', 'content': response_content},
    ]
    print('\n')  # Add space after response

    if args.verbose and last_chunk is not None:
        print_verbose_metadata(last_chunk)
        print()
