"""Exact local Qwen3.8 GGUF tokenizer, with vocabulary-only native loading.

No model context, tensor weights, inference, server, or network is used. The
ctypes structure mirrors the official header at the *installed* libllama build
commit 631109b34, and the library hash is pinned before any ABI call. Headers
were checked independently; no guessed tokenizer regex or substitute model is
used. Plain memory text defaults to literal-special-token handling; rendered
chat templates should explicitly set parse_special=True.
"""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct


DEFAULT_MODEL = Path("/home/data/models/gguf/Qwen3.8-27B-Q8_0/Qwen3.8-27B-Q8_0.gguf")
RUNTIME = Path(__file__).resolve().parents[1] / "vendor/qwen-tokenizer-631109b34"
DEFAULT_LIBRARY = RUNTIME / "lib/libllama.so.0.5.0"
LIBRARY_SHA256 = "73b89cc3cfd638b9175974fc9337ce6ad5a80272562bd933056948327188f723"
HEADER_COMMIT = "631109b34"
HEADER_URL = f"https://raw.githubusercontent.com/ggml-org/llama.cpp/{HEADER_COMMIT}/include/llama.h"
HEADERS_MANIFEST = RUNTIME / "headers-manifest.json"


class _ModelParams(C.Structure):
    # Exact struct llama_model_params from the pinned public header. All enum
    # fields have C int representation on the verified Linux x86_64 build.
    _fields_ = [
        ("devices", C.c_void_p), ("tensor_buft_overrides", C.c_void_p),
        ("n_gpu_layers", C.c_int32), ("split_mode", C.c_int),
        ("load_mode", C.c_int), ("lazy_mode", C.c_int),
        ("main_gpu", C.c_int32), ("tensor_split", C.c_void_p),
        ("progress_callback", C.c_void_p), ("progress_callback_user_data", C.c_void_p),
        ("kv_overrides", C.c_void_p), ("vocab_only", C.c_bool),
        ("check_tensors", C.c_bool), ("use_extra_bufts", C.c_bool),
        ("no_host", C.c_bool), ("no_alloc", C.c_bool), ("load_mtp", C.c_bool),
    ]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_gguf_metadata(path):
    """Read only the GGUF header/metadata; never seek into tensor data."""
    with Path(path).open("rb") as source:
        def take(size):
            value = source.read(size)
            if len(value) != size:
                raise ValueError("Truncated GGUF metadata")
            return value

        def number(fmt):
            return struct.unpack("<" + fmt, take(struct.calcsize(fmt)))[0]

        def string():
            return take(number("Q")).decode("utf-8")

        def value(kind):
            if kind == 8:
                return string()
            if kind == 9:
                subtype, count = number("I"), number("Q")
                return [value(subtype) for _ in range(count)]
            formats = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i",
                       6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
            if kind not in formats:
                raise ValueError(f"Unsupported GGUF metadata type {kind}")
            return number(formats[kind])

        if take(4) != b"GGUF" or number("I") != 3:
            raise ValueError("Expected little-endian GGUF v3")
        tensors, keys = number("Q"), number("Q")
        result = {}
        for _ in range(keys):
            key = string()
            if key in result:
                raise ValueError("Duplicate GGUF metadata key")
            result[key] = value(number("I"))
        end = source.tell()
        source.seek(0)
        metadata_sha = hashlib.sha256(take(end)).hexdigest()
    return result, {"metadata_bytes": end, "metadata_sha256": metadata_sha,
                    "declared_tensors": tensors, "metadata_keys": keys}


class LocalQwenTokenizer:
    def __init__(self, model_path=DEFAULT_MODEL, library_path=DEFAULT_LIBRARY):
        self.model_path = Path(model_path).resolve()
        self.library_path = Path(library_path).resolve()
        if C.sizeof(C.c_void_p) != 8 or C.sizeof(_ModelParams) != 80:
            raise RuntimeError("Pinned native tokenizer ABI requires the verified 64-bit layout")
        if _sha(self.library_path) != LIBRARY_SHA256:
            raise RuntimeError("Unrecognized libllama binary: verify matching headers/ABI first")
        metadata, audit = read_gguf_metadata(self.model_path)
        expected = {"general.name": "Qwen3.8-27B", "general.architecture": "qwen35",
                    "tokenizer.ggml.model": "gpt2", "tokenizer.ggml.pre": "qwen35",
                    "tokenizer.ggml.add_bos_token": False}
        if any(metadata.get(key) != expected_value for key, expected_value in expected.items()):
            raise ValueError("Local model/tokenizer metadata does not match Qwen3.8-27B")
        tokens = metadata["tokenizer.ggml.tokens"]
        if len(tokens) != 248320 or len(metadata["tokenizer.ggml.merges"]) != 247587:
            raise ValueError("Unexpected exact-model vocabulary/merges")
        self.chat_template = metadata["tokenizer.chat_template"]
        self.bos_token = tokens[metadata["tokenizer.ggml.bos_token_id"]]
        self.eos_token = tokens[metadata["tokenizer.ggml.eos_token_id"]]
        self.tokenizer_info = {**expected, "vocab_size": len(tokens), "merge_count": 247587,
            "bos_token_id": metadata["tokenizer.ggml.bos_token_id"], "bos_token": self.bos_token,
            "eos_token_id": metadata["tokenizer.ggml.eos_token_id"], "eos_token": self.eos_token,
            "chat_template": self.chat_template,
            "special_tokens": {token: index for index, (token, kind) in enumerate(zip(
                tokens, metadata["tokenizer.ggml.token_type"])) if kind == 3}}
        self._lib = C.CDLL(str(self.library_path))
        self._configure()
        self.load_log = []
        self._callback = C.CFUNCTYPE(None, C.c_int, C.c_char_p, C.c_void_p)(
            lambda level, message, _: self.load_log.append(message.decode("utf-8", errors="replace")))
        self._lib.llama_log_set(self._callback, None)
        params = self._lib.llama_model_default_params()
        params.vocab_only = True
        params.n_gpu_layers = 0
        self._model = self._lib.llama_model_load_from_file(str(self.model_path).encode(), params)
        if not self._model:
            raise RuntimeError("Native vocabulary-only load failed: " + "".join(self.load_log[-8:]))
        self._vocab = self._lib.llama_model_get_vocab(self._model)
        assert self._lib.llama_vocab_n_tokens(self._vocab) == len(tokens)
        assert self._lib.llama_vocab_bos(self._vocab) == self.tokenizer_info["bos_token_id"]
        assert self._lib.llama_vocab_eos(self._vocab) == self.tokenizer_info["eos_token_id"]
        assert any("vocab only - skipping tensors" in line for line in self.load_log)
        manifest_path = self.model_path.parent / "download.json"
        download = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        self.provenance = {
            "model": "Qwen3.8-27B", "quantization": "Q8_0", "model_path": str(self.model_path),
            "model_file_bytes": self.model_path.stat().st_size,
            "model_source": download.get("source"), "model_revision": download.get("revision"),
            "model_sha256_from_existing_download_manifest": next((entry["sha256"] for entry in download.get("files", [])
                if entry["name"] == self.model_path.name), None),
            "full_weights_rehashed": False, **audit,
            "library_path": str(self.library_path), "library_sha256": LIBRARY_SHA256,
            "library_commit": HEADER_COMMIT, "abi_header_url": HEADER_URL,
            "abi_headers_manifest": str(HEADERS_MANIFEST),
            "abi_headers": json.loads(HEADERS_MANIFEST.read_text()) if HEADERS_MANIFEST.exists() else None,
            "vocab_only": True, "tensor_weights_loaded": False, "model_context_created": False,
            "inference_calls": 0, "server_started": False,
            "tokenizer": {key: value for key, value in self.tokenizer_info.items() if key not in ("chat_template", "special_tokens")},
            "chat_template_sha256": hashlib.sha256(self.chat_template.encode()).hexdigest(),
            "ordinary_text_policy": "add_special=False, parse_special=False; no BOS/EOS or chat framing",
            "chat_text_policy": "Caller renders embedded GGUF template, then explicitly sets parse_special=True",
        }

    def _configure(self):
        signatures = {
            "llama_model_default_params": ([], _ModelParams),
            "llama_model_load_from_file": ([C.c_char_p, _ModelParams], C.c_void_p),
            "llama_model_get_vocab": ([C.c_void_p], C.c_void_p),
            "llama_model_free": ([C.c_void_p], None),
            "llama_vocab_n_tokens": ([C.c_void_p], C.c_int32),
            "llama_vocab_bos": ([C.c_void_p], C.c_int32),
            "llama_vocab_eos": ([C.c_void_p], C.c_int32),
            "llama_tokenize": ([C.c_void_p, C.c_char_p, C.c_int32, C.POINTER(C.c_int32),
                                C.c_int32, C.c_bool, C.c_bool], C.c_int32),
            "llama_log_set": ([C.CFUNCTYPE(None, C.c_int, C.c_char_p, C.c_void_p), C.c_void_p], None),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self._lib, name)
            function.argtypes, function.restype = args, result

    def encode(self, text, *, add_special=False, parse_special=False):
        if not isinstance(text, str):
            raise TypeError("Tokenization input must be text")
        if not self._model:
            raise RuntimeError("Tokenizer has been closed")
        raw = text.encode("utf-8")
        buffer = (C.c_int32 * max(8, len(raw) + 8))()
        count = self._lib.llama_tokenize(self._vocab, raw, len(raw), buffer, len(buffer),
                                        add_special, parse_special)
        if count < 0:
            buffer = (C.c_int32 * -count)()
            count = self._lib.llama_tokenize(self._vocab, raw, len(raw), buffer, len(buffer),
                                            add_special, parse_special)
        if count < 0:
            raise RuntimeError("Native tokenizer failed after buffer resize")
        return list(buffer[:count])

    def count(self, text, *, add_special=False, parse_special=False):
        return len(self.encode(text, add_special=add_special, parse_special=parse_special))

    def close(self):
        if getattr(self, "_model", None):
            self._lib.llama_model_free(self._model)
            self._model = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


if __name__ == "__main__":
    with LocalQwenTokenizer() as tokenizer:
        print(json.dumps(tokenizer.provenance, ensure_ascii=False, indent=2))
        for text in ("hello", "你好", "GraphMemory V1", "<|im_start|>", ""):
            print(repr(text), tokenizer.encode(text), tokenizer.encode(text, parse_special=True))
