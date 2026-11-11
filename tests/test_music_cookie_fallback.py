import unittest
from types import SimpleNamespace

from ums.cookie_utils import (
    _extract_info_with_cookie_fallback,
    _is_browser_cookie_access_error,
    _run_with_cookie_fallback,
)


class BrowserCookieFallbackTests(unittest.TestCase):
    def test_locked_chrome_cookie_database_is_recognized(self):
        error = RuntimeError(
            "ERROR: Could not copy Chrome cookie database. "
            "Permission denied: Profile 1/Network/Cookies"
        )
        self.assertTrue(_is_browser_cookie_access_error(error))

    def test_unrelated_authentication_failure_does_not_disable_cookies(self):
        error = RuntimeError("Sign in to confirm you are not a bot.")
        self.assertFalse(_is_browser_cookie_access_error(error))

    def test_yt_dlp_retries_once_without_locked_browser_cookies(self):
        calls = []

        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = dict(options)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                calls.append((dict(self.options), url, download))
                if "cookiesfrombrowser" in self.options:
                    raise RuntimeError(
                        "Could not copy Chrome cookie database. Permission denied."
                    )
                return {"entries": [{"id": "public-result"}]}

        search_options = {
            "quiet": True,
            "cookiesfrombrowser": ("brave", "Profile 1"),
        }
        download_options = {
            "format": "bestaudio/best",
            "cookiesfrombrowser": ("brave", "Profile 1"),
        }
        messages = []
        state = {"used": False}

        result = _extract_info_with_cookie_fallback(
            SimpleNamespace(YoutubeDL=FakeYoutubeDL),
            search_options,
            "ytsearch5:test",
            related_options=(download_options,),
            log_cb=messages.append,
            fallback_state=state,
        )

        self.assertEqual(result["entries"][0]["id"], "public-result")
        self.assertTrue(state["used"])
        self.assertNotIn("cookiesfrombrowser", search_options)
        self.assertNotIn("cookiesfrombrowser", download_options)
        self.assertEqual(len(calls), 2)
        self.assertIn("without browser cookies", messages[0])

    def test_generic_download_operation_retries_once_without_locked_cookies(self):
        options = {"cookiesfrombrowser": ("brave", "Profile 1")}
        state = {"used": False}
        calls = []
        messages = []

        def operation():
            calls.append("attempt")
            if "cookiesfrombrowser" in options:
                raise RuntimeError("Could not copy Chrome cookie database. Permission denied.")
            return "download-complete"

        result = _run_with_cookie_fallback(
            options,
            operation,
            log_cb=messages.append,
            fallback_state=state,
            task_label="download",
        )

        self.assertEqual(result, "download-complete")
        self.assertEqual(len(calls), 2)
        self.assertTrue(state["used"])
        self.assertNotIn("cookiesfrombrowser", options)
        self.assertIn("download", messages[0])

    def test_generic_runner_does_not_retry_non_cookie_errors(self):
        options = {"cookiesfrombrowser": ("brave", "Profile 1")}
        calls = []

        def operation():
            calls.append("attempt")
            raise RuntimeError("Sign in to confirm you are not a bot.")

        with self.assertRaisesRegex(RuntimeError, "Sign in"):
            _run_with_cookie_fallback(options, operation)
        self.assertEqual(len(calls), 1)
        self.assertIn("cookiesfrombrowser", options)

    def test_fallback_preserves_cookies_for_non_permission_errors(self):
        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                raise RuntimeError("Sign in to confirm you are not a bot.")

        options = {"cookiesfrombrowser": ("brave", "Profile 1")}
        with self.assertRaisesRegex(RuntimeError, "Sign in"):
            _extract_info_with_cookie_fallback(
                SimpleNamespace(YoutubeDL=FakeYoutubeDL), options, "https://youtube.com/watch?v=test"
            )
        self.assertIn("cookiesfrombrowser", options)


if __name__ == "__main__":
    unittest.main()
