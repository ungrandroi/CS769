"""Register the exact local model and invoke the unmodified official BFCL scorer."""
MODEL_KEY = "local/Qwen3.8-27B-Q8-0-FC"
SERVING_MODEL = "bfcl-qwen38-27b"


def register_models():
    from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING, ModelConfig
    from bfcl_eval.model_handler.api_inference.openai_completion import OpenAICompletionsHandler
    MODEL_CONFIG_MAPPING.setdefault(MODEL_KEY, ModelConfig(
        model_name=SERVING_MODEL, display_name="Local Qwen3.8 27B Q8_0 (FC)",
        url="https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF", org="Qwen",
        license="See original model distribution", model_handler=OpenAICompletionsHandler,
        is_fc_model=True, underscore_to_dot=True))


def main():
    import os
    # The official scorer constructs a handler for decoding only. It never
    # invokes inference; dummy loopback credentials prevent reading real keys.
    os.environ["OPENAI_API_KEY"] = "local-evaluation-no-key"
    os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:11435/v1"
    register_models()
    from bfcl_eval.__main__ import cli
    cli()

if __name__ == "__main__":main()
