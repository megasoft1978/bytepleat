import unittest

from bench_macos import independent_decode_status


class IndependentDecodeStatusTests(unittest.TestCase):
    def test_matching_success_passes(self):
        self.assertEqual(independent_decode_status({"exit_code": 0}, True), "pass")

    def test_success_with_wrong_restored_tree_fails(self):
        self.assertEqual(independent_decode_status({"exit_code": 0}, False), "fail")

    def test_explicit_unsupported_method_is_reported_separately(self):
        record = {
            "exit_code": 2,
            "timed_out": False,
            "stderr_tail": "ERROR: Unsupported Method : sample.txt\n",
        }
        self.assertEqual(independent_decode_status(record, False), "unsupported-method")

    def test_generic_decoder_error_still_fails(self):
        record = {"exit_code": 2, "timed_out": False, "stderr_tail": "ERROR: CRC Failed"}
        self.assertEqual(independent_decode_status(record, False), "fail")

    def test_unsupported_method_mixed_with_another_error_still_fails(self):
        record = {
            "exit_code": 2,
            "timed_out": False,
            "stderr_tail": "ERROR: Unsupported Method : sample.txt\nERROR: CRC Failed\n",
        }
        self.assertEqual(independent_decode_status(record, False), "fail")

    def test_unsupported_method_mixed_with_non_error_diagnostic_still_fails(self):
        record = {
            "exit_code": 2,
            "timed_out": False,
            "stderr_tail": "ERROR: Unsupported Method : sample.txt\nData Error\n",
        }
        self.assertEqual(independent_decode_status(record, False), "fail")

    def test_full_log_is_used_when_recorded_tail_was_truncated(self):
        record = {"exit_code": 2, "timed_out": False, "stderr_tail": ": trailing filename.txt"}
        full_log = "ERROR: Unsupported Method : filename.txt\n"
        self.assertEqual(independent_decode_status(record, False, full_log), "unsupported-method")

    def test_timed_out_decoder_is_never_classified_as_unsupported(self):
        record = {
            "exit_code": 2,
            "timed_out": True,
            "stderr_tail": "ERROR: Unsupported Method : sample.txt\n",
        }
        self.assertEqual(independent_decode_status(record, False), "fail")


if __name__ == "__main__":
    unittest.main()
