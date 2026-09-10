"""
Live orchestrator demo (Week 9).

Plays one conversation through the orchestrator against the real MySQL data and
OpenAI: every message is classified by the model, routed to the right agent(s),
and answered. Needs MySQL running and an API key in .env.

Usage:
    python3 demo_orchestrator.py                          # the scripted conversation
    python3 demo_orchestrator.py "Is now a good time to buy in San Diego?"
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from orchestrator import orchestrate  # noqa: E402

CONVERSATION = [
    "Find me affordable homes in Pasadena and tell me whether prices are rising.",   # mixed
    "Show me homes similar to the first one.",                                       # recommend
    "What does DOM mean?",                                                           # knowledge
    "What's the average price per sqft in Pasadena?",                                # market
    "Can you email these listings to my wife?",                                      # email
]


def main():
    messages = sys.argv[1:] or CONVERSATION
    user_id = "demo-user"
    for message in messages:
        result = orchestrate(message, user_id)
        print("=" * 72)
        print(f"USER  : {message}")
        print(f"ROUTE : {result['intent']} -> {', '.join(result['agents']) or 'no agent'}")
        print(f"\n{result['text']}\n")


if __name__ == "__main__":
    main()
