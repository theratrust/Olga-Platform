"""Generic safe transport reuse only; no methodology labels or gold semantics."""
from services.model_qualification_adapter import (
    AdapterError, ModelConfig, ModelReply, ModelParseError, OpenAICompatibleAdapter,
    parse_model_json, sanitize, backend_host,
)
