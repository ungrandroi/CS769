"""Explicit output reservations for new diagnostic continuations.

Historical prefixes keep their original generation settings. A diagnostic's
live output budget must be applied to the native request and context reservation
together; changing it never rewrites an archived prefix.
"""

DEFAULT_MAX_OUTPUT_TOKENS = 16384
MODEL_CONTEXT_TOKENS = 131072


def validate_max_output_tokens(value, context=MODEL_CONTEXT_TOKENS):
    if type(value) is not int or not 0 < value < context:
        raise ValueError(f"Output token budget must be an integer between 1 and {context - 1}")
    return value


def request_with_output_budget(factory, request, seed, max_output_tokens):
    """Override only the live native request's cap, preserving its other fields."""
    validate_max_output_tokens(max_output_tokens)
    body = factory(request, seed)
    return dict(body, max_tokens=max_output_tokens)


def fits_context(input_tokens, max_output_tokens, context=MODEL_CONTEXT_TOKENS):
    validate_max_output_tokens(max_output_tokens, context)
    if type(input_tokens) is not int or input_tokens < 0:
        raise ValueError("Input token count must be a nonnegative integer")
    return input_tokens + max_output_tokens <= context
