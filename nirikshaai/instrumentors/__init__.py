"""Hand-written instrumentors for frameworks with no upstream OTel package.

Most LLM and agent libraries already have an OpenLLMetry or OpenInference
instrumentor, and those are loaded by ``_otel._LLM_INSTRUMENTATIONS`` — adding
one there is a single line and needs no code here. This package is only for the
gaps.

Every instrumentor here emits **standard OTel GenAI attributes**
(``gen_ai.*``), because the platform already coalesces those into its
materialized ClickHouse columns. That means a correctly-attributed span lands in
the agent views, the topology graph and the loop detector with *no server-side
work at all*. Emitting a bespoke attribute name would require a schema change to
achieve the same thing.
"""

from nirikshaai.instrumentors.langgraph import (
    LangGraphInstrumentor,
    instrument_langgraph,
)

__all__ = ["LangGraphInstrumentor", "instrument_langgraph"]
