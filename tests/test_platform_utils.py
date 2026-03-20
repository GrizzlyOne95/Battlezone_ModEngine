import os
import unittest

from platform_utils import (
    get_default_steamcmd_path,
    get_popen_output_kwargs,
    get_steamcmd_candidates,
    get_steamcmd_name,
)


class FakeSubprocess:
    PIPE = object()
    STDOUT = object()
    CREATE_NO_WINDOW = 99


class PlatformUtilsTests(unittest.TestCase):
    def test_get_steamcmd_name(self):
        self.assertEqual(get_steamcmd_name(True), "steamcmd.exe")
        self.assertEqual(get_steamcmd_name(False), "steamcmd.sh")

    def test_get_default_steamcmd_path(self):
        self.assertTrue(get_default_steamcmd_path("/tmp/bin", False).endswith(os.path.join("bin", "steamcmd.sh")))

    def test_get_steamcmd_candidates_windows(self):
        candidates = get_steamcmd_candidates(r"C:\repo\bin", True, False, cwd=r"C:\repo")
        self.assertTrue(any(candidate.endswith("steamcmd.exe") for candidate in candidates))
        self.assertEqual(candidates[0], os.path.join(r"C:\repo\bin", "steamcmd.exe"))

    def test_get_steamcmd_candidates_linux(self):
        candidates = get_steamcmd_candidates("/repo/bin", False, True, home="/home/test")
        self.assertEqual(candidates[0], os.path.join("/repo/bin", "steamcmd.sh"))
        self.assertIn("/usr/bin/steamcmd", candidates)

    def test_get_popen_output_kwargs_windows_adds_flag(self):
        kwargs = get_popen_output_kwargs(True, subprocess_module=FakeSubprocess)
        self.assertEqual(kwargs["creationflags"], 99)
        self.assertIs(kwargs["stdout"], FakeSubprocess.PIPE)


if __name__ == "__main__":
    unittest.main()
