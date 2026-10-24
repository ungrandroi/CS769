"""Run the unchanged paired protocol with an exact delivered-payload codec."""
import argparse
import importlib
import json
import sys


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--codec-module')
    parser.add_argument('--codec-variant')
    custom, rest = parser.parse_known_args()
    if custom.codec_module:
        from core import optimized_graph
        original = optimized_graph.build_memory
        codec = importlib.import_module(custom.codec_module)

        def encoded_memory(history, method, explanation, count):
            _, original_meta = original(history, method, explanation, count)
            payload = original_meta['graph']
            encoded = codec.encode(payload, custom.codec_variant)
            restored = codec.decode(encoded)
            assert optimized_graph._same(payload, restored), 'Delivered payload changed'
            assert optimized_graph._same(history, optimized_graph.restore_history(restored))
            assert optimized_graph._same(
                optimized_graph.rebuild_original_graph(payload),
                optimized_graph.rebuild_original_graph(restored))
            body = optimized_graph.dumps(encoded)
            instruction = original_meta['instruction']
            text = instruction + '\n' + body if instruction else body
            meta = dict(original_meta, candidate=custom.codec_variant,
                        codec_module=custom.codec_module, encoded=encoded,
                        baseline_body=original_meta['body'],
                        baseline_body_tokens=original_meta['body_tokens'],
                        body=body, body_tokens=count(body), graph_tokens=count(body),
                        total_tokens=count(text), payload_decode_exact=True,
                        optimized_reconstruction_audit={
                            'payload_exact': True, 'history_exact': True,
                            'original_graph_rebuilt_exact': True})
            return text, meta

        optimized_graph.build_memory = encoded_memory
    sys.argv = [sys.argv[0], *rest]
    from workflows.work1000_task import main as run
    run()


if __name__ == '__main__':
    main()
