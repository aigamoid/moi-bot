import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.main import main


class StartupTests(unittest.TestCase):
    def test_dotenv_is_loaded_without_overwriting_existing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("DISCORD_TOKEN=offline-file-token\n", encoding="utf-8")
            for existing, expected in (({}, "offline-file-token"),
                                       ({"DISCORD_TOKEN": "offline-env-token"},
                                        "offline-env-token")):
                with (self.subTest(existing=bool(existing)),
                      patch.dict(os.environ, existing, clear=True),
                      patch("dotenv.main.find_dotenv", return_value=str(path)),
                      patch("bot.main.create_client") as create_client):
                    main()
                    create_client.return_value.run.assert_called_once_with(expected)

    def test_missing_token_fails_before_running_client(self):
        with (patch.dict(os.environ, {}, clear=True),
              patch("bot.main.load_dotenv"),
              patch("bot.main.create_client") as create_client):
            with self.assertRaises(KeyError):
                main()
            create_client.return_value.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
