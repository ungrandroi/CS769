"""Apply the paired-run mechanical audit to the new mixed semantic builder."""
from core import mixed_graph, optimized_graph
from workflows import lossless_audit


def main():
    # Original source-message packing is unchanged; only the semantic builder
    # used to independently regenerate the expected delivered graph differs.
    optimized_graph.build_memory = mixed_graph.build_memory
    lossless_audit.main()


if __name__ == "__main__":
    main()
