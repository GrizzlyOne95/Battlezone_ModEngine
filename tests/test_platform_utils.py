import os
import subprocess
import time
import unittest

from platform_utils import (
    get_default_steamcmd_path,
    get_popen_output_kwargs,
    get_steamcmd_candidates,
    get_steamcmd_name,
    terminate_process_tree,
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
        self.assertNotIn("start_new_session", kwargs)

    def test_get_popen_output_kwargs_posix_starts_new_session(self):
        kwargs = get_popen_output_kwargs(False, subprocess_module=FakeSubprocess)
        self.assertTrue(kwargs["start_new_session"])

    def test_terminate_process_tree_windows_uses_taskkill_tree(self):
        calls = []

        class FakeProcess:
            pid = 4321

            def __init__(self):
                self.alive = True

            def poll(self):
                return None if self.alive else 1

            def terminate(self):
                self.alive = False

        class FakeSub:
            DEVNULL = None
            SubprocessError = subprocess.SubprocessError

            @staticmethod
            def run(args, **kwargs):
                calls.append(args)

        terminate_process_tree(FakeProcess(), True, subprocess_module=FakeSub)
        self.assertEqual(calls, [["taskkill", "/F", "/T", "/PID", "4321"]])

    @unittest.skipIf(os.name == "nt", "POSIX process groups")
    def test_terminate_process_tree_kills_wrapper_children(self):
        # Mimic steamcmd.sh: a shell wrapper whose child holds stdout open.
        process = subprocess.Popen(
            ["/bin/sh", "-c", "sleep 30; echo done"],
            **get_popen_output_kwargs(False),
        )
        time.sleep(0.2)
        started = time.monotonic()
        terminate_process_tree(process, False)
        self.assertEqual(process.stdout.read(), "")  # EOF, not blocked for 30s
        process.wait(timeout=5)
        process.stdout.close()
        self.assertLess(time.monotonic() - started, 5)


if __name__ == "__main__":
    unittest.main()
