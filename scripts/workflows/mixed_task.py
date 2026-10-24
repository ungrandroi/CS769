"""One paired work-1000 run using the separately versioned mixed semantics."""
import argparse
import importlib
import sys


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--codec-module")
    parser.add_argument("--codec-variant")
    options, rest = parser.parse_known_args()
    if bool(options.codec_module) != bool(options.codec_variant):
        raise ValueError("Codec module and variant must be supplied together")
    from core import mixed_graph, optimized_graph

    def memory(history, method, explanation, count):
        text, metadata = mixed_graph.build_memory(history, method, explanation, count)
        if not options.codec_module:
            return text, metadata
        codec = importlib.import_module(options.codec_module)
        payload = metadata["graph"]
        encoded = codec.encode(payload, options.codec_variant)
        restored = codec.decode(encoded)
        if not optimized_graph._same(payload, restored):
            raise AssertionError("Encoded mixed semantic payload changed")
        if not optimized_graph._same(history, mixed_graph.restore_history(restored)):
            raise AssertionError("Mixed source history changed")
        if not optimized_graph._same(mixed_graph.rebuild_original_graph(payload),
                                     mixed_graph.rebuild_original_graph(restored)):
            raise AssertionError("Mixed original graph changed")
        body = optimized_graph.dumps(encoded)
        instruction = metadata["instruction"]
        text = instruction + "\n" + body if instruction else body
        return text, dict(
            metadata, candidate=options.codec_variant, codec_module=options.codec_module,
            encoded=encoded, baseline_body=metadata["body"],
            baseline_body_tokens=metadata["body_tokens"], body=body,
            body_tokens=count(body), graph_tokens=count(body), total_tokens=count(text),
            payload_decode_exact=True,
            optimized_reconstruction_audit=dict(payload_exact=True, history_exact=True,
                                                original_graph_rebuilt_exact=True))

    # Leave old restore/rebuild functions untouched: mixed_graph deliberately
    # reuses the historical message-table codec, not its filesystem-only builder.
    optimized_graph.build_memory = memory
    sys.argv = [sys.argv[0], *rest]
    from workflows.work1000_task import main as run
    run()


if __name__ == "__main__":
    main()
