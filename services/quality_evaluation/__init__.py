"""Offline response-quality contracts; derived product criteria, no runtime routing."""

from .contract import QualityContractError, load_corpus, validate_case, validate_input, validate_result

__all__ = ["QualityContractError", "load_corpus", "validate_case", "validate_input", "validate_result"]
