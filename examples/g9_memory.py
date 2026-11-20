"""Run from the repository root: PYTHONPATH=scripts python3 examples/g9_memory.py.

Synthetic tool records only. This example makes no API calls.
"""
import argparse
import json

from core.g9_memory import build_g9_memory


def example_history():
    return [
        {"role": "user", "content": "Buy two shares of MSFT and check the order."},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_demo_1", "type": "function", "function": {
                "name": "place_order",
                "arguments": '{"symbol":"MSFT","amount":2}',
            }},
        ]},
        {"role": "tool", "tool_call_id": "call_demo_1",
         "content": '{"order_id":12446,"status":"Pending"}'},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_demo_2", "type": "function", "function": {
                "name": "get_order_details", "arguments": '{"order_id":12446}',
            }},
        ]},
        {"role": "tool", "tool_call_id": "call_demo_2",
         "content": '{"id":12446,"status":"Completed"}'},
        {"role": "assistant", "content": "Order 12446 is completed."},
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("working-history", "completed-turn"),
                        default="working-history")
    args = parser.parse_args()
    history = example_history()
    if args.profile == "working-history":
        # Safe checkpoint after the last tool result, before the assistant finishes.
        history = history[:-1]
    memory = build_g9_memory(history, history, provider="openai")
    messages = [{"role": "system", "content": "You are a tool-using assistant."}]
    if args.profile == "working-history":
        messages.append({"role": "user", "content": memory["memory_text"]})
    else:
        messages.extend([
            {"role": "assistant", "content": memory["memory_text"]},
            {"role": "user", "content": "What was that order's final status?"},
        ])
    print(json.dumps(messages, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
