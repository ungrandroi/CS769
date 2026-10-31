"""Run from the repository root: PYTHONPATH=scripts python3 examples/g9_memory.py.

Synthetic tool records only. This example makes no API calls.
"""
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
    history = example_history()
    memory = build_g9_memory(history, history, provider="openai")
    # Complete illustrative message list; the archived history is NOT appended.
    messages = [
        {"role": "system", "content": "You are a tool-using assistant."},
        {"role": "assistant", "content": memory["memory_text"]},
        {"role": "user", "content": "What was that order's final status?"},
    ]
    print(json.dumps(messages, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
