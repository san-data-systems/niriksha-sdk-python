"""A small agent wrapped with observe / span / log.

Run it against any NirikshaAI install and it shows up on LLM → Runs within a
few seconds, with a timeline, a repeated-tool finding (we call `search` four
times in a row on purpose) and one error.

    NIRIKSHA_ENDPOINT=https://app.niriksha.ai NIRIKSHA_API_KEY=nai_... python agent.py
"""

from __future__ import annotations

import os
import random
import time

import nirikshaai
from nirikshaai import log, observe, span

nirikshaai.init(
    endpoint=os.environ["NIRIKSHA_ENDPOINT"],
    api_key=os.environ["NIRIKSHA_API_KEY"],
    service_name="example-research-agent",
    otlp_endpoint=os.environ.get("NIRIKSHA_OTLP_ENDPOINT"),
)


def call_model(prompt: str) -> str:
    time.sleep(0.2)
    return f"answer to: {prompt[:40]}"


def search(query: str) -> list[str]:
    time.sleep(0.1)
    if random.random() < 0.2:
        raise RuntimeError("search backend timed out")
    return [f"doc about {query}"]


@observe("research-agent")
def run(question: str) -> str:
    log("info", "agent started", {"question": question})
    plan = span(
        "plan", lambda: call_model(f"plan for {question}"), type="llm", model="example-model"
    )
    docs: list[str] = []
    for i in range(4):  # four consecutive calls → a possible_loop finding at the default threshold
        try:
            docs += span("search", lambda: search(f"{plan} #{i}"), type="tool")
        except RuntimeError as exc:
            log("warn", "search failed, continuing", {"error": str(exc)})
    return span("answer", lambda: call_model(" ".join(docs)), type="llm", model="example-model")


if __name__ == "__main__":
    print(run("Why is the checkout service slow?"))
    nirikshaai.shutdown() if hasattr(nirikshaai, "shutdown") else None
