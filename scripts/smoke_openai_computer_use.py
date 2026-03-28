from __future__ import annotations

import json
import os

from src.screening.config import load_local_env
from src.screening.gpt54_adapter import OpenAIComputerAgent


def main() -> None:
    load_local_env()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing. Set it in the shell or in .env/.env.local.")

    agent = OpenAIComputerAgent()
    session_id = agent.start_session()
    try:
        response = agent.client.responses.create(
            model=agent.model,
            tools=[agent._tool_spec()],
            instructions=(
                "You are running a smoke test for browser automation. "
                "Do not click, type, submit, download, or navigate away. "
                "Look at the provided screenshot and return only JSON with keys "
                "blocked, reason, current_url, and page_summary."
            ),
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Inspect the current page without interacting and summarize what is visible."},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{agent.runtime.screenshot_base64()}",
                        },
                    ],
                }
            ],
            reasoning={"summary": "concise"},
            truncation="auto",
        )
        print(json.dumps(
            {
                "session_id": session_id,
                "current_url": agent.runtime.current_url,
                "models": agent.runtime_config(),
                "response_id": getattr(response, "id", None),
                "response_text": agent._response_text(response),
            },
            ensure_ascii=False,
            indent=2,
        ))
    finally:
        agent.stop_session()


if __name__ == "__main__":
    main()
