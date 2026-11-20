"""Offline candidate audit on exposed diagnostic prefixes; no model generation.

Native tokenizers load vocabulary only on CPU. Complete prompts retain the
archived native template and tools; only the single memory message is replaced.
All archived control prompt counts must match before candidate costs are used.
"""
import argparse
from collections import defaultdict
import ctypes as C
import hashlib
import json
from pathlib import Path
from statistics import mean

from core.local_qwen_tokenizer import (LocalQwenTokenizer, DEFAULT_LIBRARY,
                                      LIBRARY_SHA256, read_gguf_metadata)
from core.optimized_graph import _same, dumps
from core.readout_candidate import prepare, expand_event_index
from core.diagnostic_views import state_index


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class MuseVocab(LocalQwenTokenizer):
    """Reuse the pinned native ABI, with Muse's vocabulary and BOS behavior."""
    def __init__(self, path):
        assert C.sizeof(C.c_void_p) == 8 and sha(DEFAULT_LIBRARY) == LIBRARY_SHA256
        self.model_path = Path(path)
        metadata, self.metadata_audit = read_gguf_metadata(path)
        self._lib = C.CDLL(str(DEFAULT_LIBRARY))
        self._configure()
        self.load_log = []
        self._callback = C.CFUNCTYPE(None, C.c_int, C.c_char_p, C.c_void_p)(
            lambda level, message, _: self.load_log.append(message.decode(errors="replace")))
        self._lib.llama_log_set(self._callback, None)
        params = self._lib.llama_model_default_params()
        params.vocab_only = True
        params.n_gpu_layers = 0
        self._model = self._lib.llama_model_load_from_file(str(path).encode(), params)
        if not self._model:
            raise RuntimeError("Muse vocabulary-only load failed")
        self._vocab = self._lib.llama_model_get_vocab(self._model)
        assert self._lib.llama_vocab_n_tokens(self._vocab) == len(metadata["tokenizer.ggml.tokens"])
        assert self._lib.llama_vocab_bos(self._vocab) == metadata["tokenizer.ggml.bos_token_id"]
        assert any("vocab only - skipping tensors" in line for line in self.load_log)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise RuntimeError("Use a new output directory; never overwrite an experiment")
    out.mkdir(parents=True, exist_ok=True)
    project = Path(__file__).resolve().parents[2]
    roots = {"qwen": "mixed_history_diagnostics_v2", "muse": "muse_history_diagnostics_v2"}
    rows, pins, max_saved = [], {}, {}
    for model, folder in roots.items():
        root = project / "experiments/bfcl_identity" / folder
        plan = read(root / "task-split.json")
        contract = read(root / "runtime/runtime-contract.json")
        for p in [root / "task-split.json", root / "runtime/runtime-contract.json", root / "release.json"]:
            pins[str(p)] = sha(p)
        tok = LocalQwenTokenizer() if model == "qwen" else MuseVocab(contract["model"]["path"])
        def count(s, native=False):
            return tok.count(s, parse_special=native, add_special=native and model == "muse")
        try:
            for sample in plan["samples"]:
                case = root / "evaluation" / sample["case_id"]
                history_path = Path(sample["source_paths"]["identity"]) / "checkpoint-history.json"
                history = read(history_path)
                pins[str(history_path)] = sha(history_path)
                identity = read(case / "identity/identity_reference/accounting.json")[0]["input_tokens"]
                for method in ("state", "event", "dedup"):
                    meta_path = Path(sample["source_paths"][method + "-optimized"]) / "memory-metadata.json"
                    metadata = read(meta_path)
                    pins[str(meta_path)] = sha(meta_path)
                    control_path = case / method / "index_control"
                    old_meta = read(control_path / "memory-metadata.json")
                    old_prompt = (control_path / "initial-native-prompt.txt").read_text()
                    control_tokens = read(control_path / "accounting.json")[0]["input_tokens"]
                    assert count(old_prompt, True) == control_tokens, (model, sample["case_id"], "control tokenizer mismatch")
                    content = old_meta["replacement_messages"]
                    assert len(content) == 1 and content[0]["role"] == "user"
                    old_text = content[0]["content"]
                    assert old_prompt.count(old_text) == 1
                    for with_index in ([False, True] if method == "event" else [False]):
                        replacement, meta = prepare(history, metadata, method, event_index=with_index)
                        assert meta["body"] == old_meta["body"]
                        text = replacement[0]["content"]
                        # Message roles, boundaries, tools and all native framing
                        # stay identical; no new template branch is introduced.
                        prompt = old_prompt.replace(old_text, text, 1)
                        assert prompt.replace(text, old_text, 1) == old_prompt
                        native_tokens = count(prompt, True)
                        view_tokens = old_index_tokens = index_reference_tokens = None
                        if with_index:
                            source_index = state_index(metadata["graph"])
                            if meta["view"] is not None:
                                assert _same(expand_event_index(meta["view"], metadata["graph"]), source_index["view"])
                                view_tokens = count(dumps(meta["view"]))
                            else:
                                assert source_index["audit"]["eligible_entries"] == 0
                                view_tokens = 0
                            old_index_tokens = count(dumps(source_index["view"]))
                            original = case / method / "index_view"
                            original_prompt = (original / "initial-native-prompt.txt").read_text()
                            index_reference_tokens = read(original / "accounting.json")[0]["input_tokens"]
                            assert count(original_prompt, True) == index_reference_tokens
                        candidate = method + ("-compact-index" if with_index else "-minimal-base")
                        row = dict(model=model, case_id=sample["case_id"], task=sample["task"],
                                   family=sample["family"], seed=sample["seed"], candidate=candidate,
                                   identity_input_tokens=identity, full_input_tokens=native_tokens,
                                   diagnostic_control_tokens=control_tokens,
                                   diagnostic_index_tokens=index_reference_tokens,
                                   compact_index_tokens=view_tokens, old_index_tokens=old_index_tokens,
                                   instruction_tokens=count(meta["instruction"]),
                                   full_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                                   graph_and_history_exact=True, added_goal_copies=0,
                                   context_fits_16k_output=native_tokens+16384 <= 131072)
                        rows.append(row)
                        # A representative native prompt per model/candidate,
                        # chosen by lexical case ID (not by score or savings).
                        key = model + "/" + candidate
                        if key not in max_saved or sample["case_id"] < max_saved[key]:
                            dest = out / "examples" / model / candidate
                            dest.mkdir(parents=True, exist_ok=True)
                            (dest / "native-prompt.txt").write_text(prompt)
                            (dest / "metadata.json").write_text(json.dumps(dict(row=row, metadata=meta), indent=2)+"\n")
                            max_saved[key] = sample["case_id"]
            print(model, "offline complete", len(plan["samples"]), flush=True)
        finally:
            tok.close()
    groups = defaultdict(list)
    for row in rows:
        groups[row["model"] + "/" + row["candidate"]].append(row)
    summaries = {}
    for key, group in groups.items():
        avg = mean(r["full_input_tokens"] for r in group)
        identity = mean(r["identity_input_tokens"] for r in group)
        baseline = mean(r["diagnostic_control_tokens"] for r in group)
        summaries[key] = dict(n=len(group), mean_full_boundary_input=avg,
                              identity_mean_boundary_input=identity,
                              relative_to_identity=avg/identity-1,
                              mean_saved_vs_diagnostic_index_control=baseline-avg,
                              min_saved_vs_diagnostic_index_control=min(r["diagnostic_control_tokens"]-r["full_input_tokens"] for r in group))
        if group[0]["diagnostic_index_tokens"] is not None:
            summaries[key].update(mean_saved_vs_original_index=mean(r["diagnostic_index_tokens"]-r["full_input_tokens"] for r in group),
                                  old_index_mean=mean(r["old_index_tokens"] for r in group),
                                  compact_index_mean=mean(r["compact_index_tokens"] for r in group))
    for path, digest in pins.items():
        assert sha(path) == digest, "Source changed during audit"
    assert len(rows) == 704 and all(r["context_fits_16k_output"] for r in rows)
    report = dict(status="offline_pass_online_not_run", inference_calls=0, server_started=False,
                  gpu_weights_loaded=False, prefixes=176, candidate_inputs=len(rows),
                  source_sha256=pins, summaries=summaries, rows=rows,
                  limits=["Previously exposed diagnostic prefixes, not held-out validation.",
                          "Boundary inputs only; no claims about later-path mean input, success, or call counts.",
                          "Complete graph/history and exact previous index preserved; semantic adapter correctness not newly established.",
                          "Minimal bases remove diagnostic-only rules and are controls, not newly invented codecs."])
    (out / "offline-audit.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == "__main__":
    main()
