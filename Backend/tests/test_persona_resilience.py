import unittest

from Backend.Persona import _bounded_analysis_batches, _compact_batch_for_llm, _local_extract_batch


class PersonaResilienceTests(unittest.TestCase):
    def test_model_work_is_bounded_for_large_histories(self):
        batches = [[{"id": str(index), "text": "message"}] for index in range(100)]
        selected = _bounded_analysis_batches(batches)
        self.assertEqual(len(selected), 8)
        self.assertEqual(selected[0][0]["id"], "0")
        self.assertEqual(selected[-1][0]["id"], "99")

    def test_local_extraction_returns_mergeable_signals(self):
        result = _local_extract_batch([
            {"id": "m1", "text": "We should plan the next step because this option matters."},
            {"id": "m2", "text": "Why do you think this is the right decision?"},
        ])
        self.assertIn("dimension_signals", result)
        self.assertTrue(result["topics"])
        self.assertTrue(result["observations"])
        self.assertEqual(result["topics"][0]["evidence_ids"], ["m1", "m2"])

    def test_llm_receives_bounded_increment_not_the_full_batch(self):
        batch = [{"id": str(index), "text": "x" * 5000} for index in range(40)]
        compact = _compact_batch_for_llm(batch)
        self.assertEqual(compact["batch_message_count"], 40)
        self.assertLessEqual(len(compact["representative_messages"]), 8)
        self.assertTrue(all(len(item["text"]) <= 700 for item in compact["representative_messages"]))


if __name__ == "__main__":
    unittest.main()
