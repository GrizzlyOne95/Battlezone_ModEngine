import os
import tempfile
import unittest

from deploy_utils import (
    build_content_dir,
    build_game_context,
    build_mod_cache_path,
    clear_directory_contents,
    ensure_cache_root,
    get_cache_marker_path,
    is_safe_cache_root,
    normalize_path,
    paths_match,
)


class DeployUtilsTests(unittest.TestCase):
    def test_normalize_path_empty(self):
        self.assertEqual(normalize_path(""), "")

    def test_paths_match_uses_normalized_absolute_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            nested = os.path.join(temp_dir, "mods")
            os.makedirs(nested)
            self.assertTrue(paths_match(nested, os.path.join(temp_dir, ".", "mods")))

    def test_build_game_context_preserves_game_fields(self):
        games = {
            "BZ98R": {
                "name": "Battlezone 98 Redux",
                "appid": "301650",
                "exe": "battlezone98redux.exe",
            }
        }
        context = build_game_context(games, "BZ98R", r"C:\Games\BZ98R")
        self.assertEqual(context["name"], "Battlezone 98 Redux")
        self.assertEqual(context["appid"], "301650")
        self.assertEqual(context["exe"], "battlezone98redux.exe")
        self.assertTrue(context["game_path"].endswith(os.path.join("Games", "BZ98R")))

    def test_build_mod_cache_path_uses_expected_structure(self):
        cache_root = os.path.join("cache")
        appid = "301650"
        mid = "123"
        self.assertEqual(
            build_content_dir(cache_root, appid),
            os.path.join("cache", "steamapps", "workshop", "content", "301650"),
        )
        self.assertEqual(
            build_mod_cache_path(cache_root, appid, mid),
            os.path.join("cache", "steamapps", "workshop", "content", "301650", "123"),
        )

    def test_ensure_cache_root_creates_marker_and_marks_safe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_root = os.path.join(temp_dir, "cache")
            ensured = ensure_cache_root(cache_root, ".marker", "ok\n")
            marker = get_cache_marker_path(ensured, ".marker")
            self.assertTrue(os.path.isdir(ensured))
            self.assertTrue(os.path.isfile(marker))
            self.assertTrue(is_safe_cache_root(ensured, ".marker"))

    def test_clear_directory_contents_preserves_requested_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            keep = os.path.join(temp_dir, ".marker")
            remove = os.path.join(temp_dir, "old.txt")
            with open(keep, "w", encoding="utf-8") as handle:
                handle.write("keep")
            with open(remove, "w", encoding="utf-8") as handle:
                handle.write("remove")

            removed = []

            def remove_path(path):
                removed.append(os.path.basename(path))
                os.remove(path)

            clear_directory_contents(temp_dir, remove_path, preserve_names={".marker"})
            self.assertTrue(os.path.exists(keep))
            self.assertFalse(os.path.exists(remove))
            self.assertEqual(removed, ["old.txt"])


if __name__ == "__main__":
    unittest.main()
