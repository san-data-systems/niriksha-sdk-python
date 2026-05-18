"""OpenAI RAG-style question-answering — NirikshaAI LLM observability example.

Demonstrates:
- nirikshaai.init() with enable_llm=True for automatic LLM tracing
- nirikshaai.get_prompt() to fetch a managed prompt template
- Making an OpenAI chat completion
- Extracting the active trace ID from the current span
- Submitting a faithfulness eval linked to that trace
"""

import logging
import os

import nirikshaai
from openai import OpenAI
from opentelemetry import trace

# ---------------------------------------------------------------------------
# Initialise NirikshaAI with LLM auto-instrumentation enabled.
# This must happen before any OpenAI client calls.
# ---------------------------------------------------------------------------
nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    otlp_endpoint="ingest.niriksha.ai:4317",
    api_key=os.environ["NIRIKSHA_API_KEY"],
    service_name="rag-qa-service",
    environment=os.getenv("APP_ENV", "production"),
    enable_llm=True,
    # capture_prompts=True  # uncomment to record prompt/completion text
)

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("rag-qa")

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
tracer = trace.get_tracer("rag-qa-service")

# ---------------------------------------------------------------------------
# Simulated retrieval — replace with a real vector DB query.
# ---------------------------------------------------------------------------
_CONTEXT_DOCS = [
    "NirikshaAI is an AI-native observability platform for logs, metrics, and traces.",
    "The platform supports OpenTelemetry out of the box and provides GenAI tracing.",
    "Users can submit evaluation results via nirikshaai.submit_eval() after each LLM call.",
]


def retrieve(question: str) -> str:
    """Return a context string from the knowledge base (simplified BM25 stub)."""
    return "\n".join(f"- {doc}" for doc in _CONTEXT_DOCS)


def answer_question(question: str) -> str:
    with tracer.start_as_current_span("rag.answer") as span:
        span.set_attribute("rag.question_length", len(question))

        # Fetch a versioned prompt template from the NirikshaAI prompt vault.
        # Falls back to an inline template when the vault is unreachable.
        try:
            system_prompt = nirikshaai.get_prompt(
                "rag-system-prompt",
                variables={"context": retrieve(question)},
            )
        except ValueError:
            log.warning("prompt vault unreachable — using inline fallback")
            context = retrieve(question)
            system_prompt = (
                f"You are a helpful assistant. Answer using ONLY the context below.\n\n"
                f"Context:\n{context}"
            )

        log.info("calling OpenAI", extra={"question": question})
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.2,
            max_tokens=256,
        )
        answer = response.choices[0].message.content or ""
        span.set_attribute("rag.answer_length", len(answer))

        # Get the active trace ID to link the eval back to this span.
        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x")

        # Submit a faithfulness eval — score how well the answer sticks to context.
        # In production you would run an LLM judge here instead of a fixed score.
        eval_result = nirikshaai.submit_eval(
            trace_id=trace_id,
            metric_name="faithfulness",
            score=0.9,
            label="pass",
            explanation="Answer references only information present in the retrieved context.",
            eval_type="rule_based",
        )
        log.info("eval submitted", extra={"trace_id": trace_id, "eval": eval_result})
        return answer


def main() -> None:
    question = os.getenv("QUESTION", "What is NirikshaAI and how does it handle LLM tracing?")
    log.info("question", extra={"q": question})
    answer = answer_question(question)
    print(f"\nQ: {question}\nA: {answer}\n")


if __name__ == "__main__":
    main()
