import unittest
from io import BytesIO
from zipfile import ZipFile

from Backend.ChatImport import analyze_upload


class ChatImportTests(unittest.TestCase):
    def test_whatsapp_zip_uses_chat_text_and_ignores_media(self):
        chat = "\n".join([
            "[01/01/26, 10:00:00] A: Hello there",
            "[01/01/26, 10:01:00] B: We should plan the next step because it matters",
            "[01/01/26, 10:02:00] A: Why do you think that?",
            "[01/01/26, 10:03:00] B: Thanks for the idea",
            "[01/01/26, 10:04:00] A: Let us decide tomorrow",
        ])
        archive = BytesIO()
        with ZipFile(archive, "w") as zipped:
            zipped.writestr("WhatsApp Images/photo.jpg", b"not chat data")
            zipped.writestr("WhatsApp Chat/_chat.txt", chat)
        result = analyze_upload("whatsapp-export.zip", archive.getvalue())
        self.assertEqual(result["format"], "WhatsApp ZIP")
        self.assertEqual(result["message_count"], 5)

    def test_whatsapp_export_is_reduced_to_scoped_statistics(self):
        content = "\n".join([
            "1/1/2026, 10:00 - A: Hello there",
            "1/1/2026, 10:01 - B: We should plan the next step because it matters",
            "1/1/2026, 10:02 - A: Why do you think that?",
            "1/1/2026, 10:03 - B: Thanks for the idea",
            "1/1/2026, 10:04 - A: Let us decide tomorrow",
        ]).encode()
        result = analyze_upload("export.txt", content)
        self.assertEqual(result["format"], "WhatsApp TXT")
        self.assertEqual(result["message_count"], 5)
        self.assertGreater(result["word_count"], 10)
        self.assertTrue(result["observations"])
        self.assertIn("heatmap", result["behavior"])
        self.assertIn("decision_style", result["behavior"])
        self.assertIn("topic_graph", result)
        self.assertNotIn("ai", result)
        self.assertNotIn("_ai_samples", result)

    def test_telegram_export_supports_rich_text_parts(self):
        content = b'{"messages":[{"type":"message","date":"2026-01-01T10:00:00","from":"A","text":["Hello ",{"type":"plain","text":"world"}]},{"type":"message","date":"2026-01-01T10:01:00","from":"B","text":"One"},{"type":"message","date":"2026-01-01T10:02:00","from":"A","text":"Two"},{"type":"message","date":"2026-01-01T10:03:00","from":"B","text":"Three"},{"type":"message","date":"2026-01-01T10:04:00","from":"A","text":"Four"}]}'
        result = analyze_upload("result.json", content)
        self.assertEqual(result["format"], "Telegram JSON")
        self.assertEqual(result["message_count"], 5)
        self.assertEqual(result["participant_count"], 2)


if __name__ == "__main__":
    unittest.main()
