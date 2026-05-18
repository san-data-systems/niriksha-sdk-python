# OpenAI RAG Question-Answering

A RAG-style (Retrieval-Augmented Generation) question-answering script using OpenAI `gpt-4o-mini`. It demonstrates NirikshaAI LLM observability end-to-end: the SDK auto-instruments OpenAI calls, fetches a managed prompt template from the NirikshaAI prompt vault, extracts the active OTEL trace ID, and submits a faithfulness eval result linked to that trace.

## Prerequisites

- Python 3.11+
- An OpenAI API key
- A NirikshaAI account at [app.niriksha.ai](https://app.niriksha.ai)
- A project API key (prefix `nai_`)
- (Optional) A prompt template named `rag-system-prompt` in the NirikshaAI Prompt Management UI. The script falls back to an inline prompt if the vault is unreachable.

## Install

```bash
cd examples/llm-openai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install ../../   # install local nirikshaai SDK
```

## Run

```bash
export NIRIKSHA_API_KEY=nai_your_key_here
export OPENAI_API_KEY=sk-...
python main.py

# Ask a custom question
QUESTION="How do I submit an eval in NirikshaAI?" python main.py
```

## What you'll see in NirikshaAI

- **Traces** — A `rag.answer` span wraps the entire pipeline. Inside it, `opentelemetry-instrumentation-openai` adds a child span for the OpenAI chat completion call, recording model name, token counts, and finish reason automatically.
- **GenAI Metrics** — Token usage per model and per trace is aggregated on the GenAI > Metrics page.
- **Prompt Management** — The `rag-system-prompt` template version used for each request is recorded alongside the trace, enabling A/B comparison between prompt versions.
- **Evals** — A `faithfulness` eval result (score 0.9, label "pass") appears under GenAI > Evals, linked to the trace ID so you can click through from the eval to the full trace waterfall.
