"""Native-tokenizer sanity checks; no weights, model context, or inference."""
import unittest
from local_qwen_tokenizer import LocalQwenTokenizer


class LocalQwenTokenizerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer = LocalQwenTokenizer()

    @classmethod
    def tearDownClass(cls):
        cls.tokenizer.close()

    def test_exact_metadata_and_vocab_only_loading(self):
        t = self.tokenizer
        self.assertEqual(t.provenance['model'], 'Qwen3.8-27B')
        self.assertEqual(t.tokenizer_info['vocab_size'], 248320)
        self.assertTrue(any('vocab only - skipping tensors' in line for line in t.load_log))
        self.assertFalse(t.provenance['tensor_weights_loaded'])
        self.assertFalse(t.provenance['model_context_created'])

    def test_known_native_samples_and_empty_text(self):
        t = self.tokenizer
        self.assertEqual(t.encode('hello'), [14556])
        self.assertEqual(t.encode('你好'), [109266])
        self.assertEqual(t.encode(''), [])

    def test_control_tokens_are_explicit(self):
        t = self.tokenizer
        self.assertEqual(t.count('<|im_start|>'), 6)
        self.assertEqual(t.encode('<|im_start|>', parse_special=True), [248045])
        self.assertEqual(t.encode('hello', add_special=False), t.encode('hello', add_special=True))

    def test_unicode_null_bytes_and_deterministic_counting(self):
        t = self.tokenizer
        for text in ['中文🙂\n"quote"\\path', '\x00a\x00b', 'λ² ≤ 0.001', 'a'*10000]:
            first = t.encode(text)
            self.assertEqual(first, t.encode(text))
            self.assertEqual(len(first), t.count(text))
        with self.assertRaises(TypeError):t.count(None)


if __name__ == '__main__':unittest.main()
