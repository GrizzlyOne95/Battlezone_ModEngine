import os
import tempfile
import unittest

from deploy_utils import (
    build_content_dir,
    build_game_context,
    build_mod_cache_path,
    clear_directory_contents,
    collect_workshop_mod_sources,
    create_directory_link,
    deploy_mod,
    ensure_cache_root,
    get_cache_marker_path,
    get_latest_mtime,
    is_link_or_junction,
    is_safe_cache_root,
    is_same_or_nested_path,
    list_unexpected_cache_entries,
    normalize_path,
    paths_match,
    paths_overlap,
    remove_path,
)


def _write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _strict_remove(path):
    remove_path(path, os.path.islink)


def _symlink(src, dst):
    os.symlink(src, dst, target_is_directory=True)


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
        with tempfile.TemporaryDirectory() as temp_dir:
            game_dir = os.path.join(temp_dir, "Games", "BZ98R")
            context = build_game_context(games, "BZ98R", game_dir)
            self.assertEqual(context["name"], "Battlezone 98 Redux")
            self.assertEqual(context["appid"], "301650")
            self.assertEqual(context["exe"], "battlezone98redux.exe")
            self.assertEqual(context["game_path"], os.path.abspath(game_dir))

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

    def test_collect_workshop_mod_sources_prefers_managed_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_content = os.path.join(temp_dir, "cache_content")
            steam_content = os.path.join(temp_dir, "steam_content")
            os.makedirs(os.path.join(cache_content, "111"))
            os.makedirs(os.path.join(steam_content, "111"))
            os.makedirs(os.path.join(steam_content, "222"))

            sources = collect_workshop_mod_sources(
                cache_content,
                [steam_content],
            )

            self.assertEqual(sources["111"]["source"], "cache")
            self.assertEqual(
                sources["111"]["path"],
                os.path.normpath(os.path.join(cache_content, "111")),
            )
            self.assertEqual(sources["222"]["source"], "steam")
            self.assertEqual(
                sources["222"]["path"],
                os.path.normpath(os.path.join(steam_content, "222")),
            )

    def test_collect_workshop_mod_sources_ignores_duplicate_source_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            content_dir = os.path.join(temp_dir, "content")
            os.makedirs(os.path.join(content_dir, "333"))
            sources = collect_workshop_mod_sources(content_dir, [content_dir])
            self.assertEqual(list(sources), ["333"])
            self.assertEqual(sources["333"]["source"], "cache")

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


    def test_ensure_cache_root_never_marks_folder_with_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write(os.path.join(temp_dir, "Documents", "thesis.docx"))
            ensure_cache_root(temp_dir, ".marker", "ok\n")
            self.assertFalse(os.path.exists(get_cache_marker_path(temp_dir, ".marker")))
            self.assertFalse(is_safe_cache_root(temp_dir, ".marker"))

    def test_ensure_cache_root_adopts_existing_steamcmd_only_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, "steamapps", "workshop"))
            ensure_cache_root(temp_dir, ".marker", "ok\n")
            self.assertTrue(is_safe_cache_root(temp_dir, ".marker"))

    def test_list_unexpected_cache_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, "steamapps"))
            _write(os.path.join(temp_dir, ".marker"))
            self.assertEqual(list_unexpected_cache_entries(temp_dir, ".marker"), [])
            _write(os.path.join(temp_dir, "notes.txt"))
            self.assertEqual(list_unexpected_cache_entries(temp_dir, ".marker"), ["notes.txt"])
            self.assertIsNone(list_unexpected_cache_entries(os.path.join(temp_dir, "missing"), ".marker"))

    def test_path_nesting_and_overlap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = os.path.join(temp_dir, "Games")
            child = os.path.join(parent, "BZ98R")
            sibling = os.path.join(temp_dir, "GamesOther")
            self.assertTrue(is_same_or_nested_path(parent, child))
            self.assertTrue(is_same_or_nested_path(parent, parent))
            self.assertFalse(is_same_or_nested_path(child, parent))
            self.assertFalse(is_same_or_nested_path(parent, sibling))
            self.assertTrue(paths_overlap(child, parent))
            self.assertFalse(paths_overlap(parent, sibling))
            self.assertFalse(paths_overlap("", parent))

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_remove_path_unlinks_symlink_and_keeps_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = os.path.join(temp_dir, "cache", "123")
            _write(os.path.join(target, "mod.txt"))
            link = os.path.join(temp_dir, "mods", "123")
            os.makedirs(os.path.dirname(link))
            _symlink(target, link)

            _strict_remove(link)
            self.assertFalse(os.path.lexists(link))
            self.assertTrue(os.path.isfile(os.path.join(target, "mod.txt")))

    def test_remove_path_deletes_physical_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            copy = os.path.join(temp_dir, "mods", "123")
            _write(os.path.join(copy, "sub", "mod.txt"))
            _strict_remove(copy)
            self.assertFalse(os.path.exists(copy))

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_deploy_mod_link_mode_replaces_stale_physical_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = os.path.join(temp_dir, "cache", "123")
            _write(os.path.join(src, "new.txt"))
            dst = os.path.join(temp_dir, "mods", "123")
            _write(os.path.join(dst, "old.txt"))

            self.assertTrue(deploy_mod(src, dst, False, _strict_remove, _symlink))
            self.assertTrue(os.path.islink(dst))
            self.assertEqual(os.listdir(dst), ["new.txt"])

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_deploy_mod_link_mode_repairs_dangling_link(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = os.path.join(temp_dir, "cache", "123")
            _write(os.path.join(src, "mod.txt"))
            dst = os.path.join(temp_dir, "mods", "123")
            os.makedirs(os.path.dirname(dst))
            _symlink(os.path.join(temp_dir, "gone"), dst)

            self.assertTrue(deploy_mod(src, dst, False, _strict_remove, _symlink))
            self.assertTrue(os.path.exists(os.path.join(dst, "mod.txt")))

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_deploy_mod_link_mode_keeps_valid_link(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = os.path.join(temp_dir, "cache", "123")
            other = os.path.join(temp_dir, "steam", "123")
            _write(os.path.join(src, "a.txt"))
            _write(os.path.join(other, "b.txt"))
            dst = os.path.join(temp_dir, "mods", "123")
            os.makedirs(os.path.dirname(dst))
            _symlink(other, dst)

            calls = []
            self.assertTrue(deploy_mod(src, dst, False, _strict_remove, lambda s, d: calls.append(s)))
            self.assertEqual(calls, [])
            self.assertEqual(os.readlink(dst), other)

    def test_deploy_mod_physical_mode_replaces_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = os.path.join(temp_dir, "cache", "123")
            _write(os.path.join(src, "new.txt"))
            dst = os.path.join(temp_dir, "mods", "123")
            _write(os.path.join(dst, "old.txt"))

            self.assertTrue(deploy_mod(src, dst, True, _strict_remove, None))
            self.assertEqual(os.listdir(dst), ["new.txt"])

    def test_deploy_mod_missing_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertFalse(deploy_mod(os.path.join(temp_dir, "nope"), os.path.join(temp_dir, "d"), True, None, None))

    def test_create_directory_link_windows_uses_create_junction_not_shell(self):
        calls = []

        class FakeWinApi:
            @staticmethod
            def CreateJunction(src, dst):
                calls.append((src, dst))

        src = os.path.join("cache", "Tom&Jerry", "123")
        dst = os.path.join("game", "mods", "123")
        create_directory_link(src, dst, True, winapi_module=FakeWinApi)
        self.assertEqual(calls, [(os.path.abspath(src), os.path.abspath(dst))])

    def test_is_link_or_junction_uses_reparse_attribute_on_windows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertTrue(is_link_or_junction(temp_dir, True, lambda p: 0x10 | 0x400))
            self.assertFalse(is_link_or_junction(temp_dir, True, lambda p: 0x10))
            # INVALID_FILE_ATTRIBUTES must not be mistaken for a junction.
            self.assertFalse(is_link_or_junction(temp_dir, True, lambda p: 0xFFFFFFFF))
            self.assertFalse(is_link_or_junction(temp_dir, True, lambda p: -1))  # ctypes signed int
            self.assertFalse(is_link_or_junction(os.path.join(temp_dir, "missing"), True, lambda p: 0x400))
            self.assertFalse(is_link_or_junction(temp_dir, False))

    def test_get_latest_mtime_sees_nested_file_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            nested = os.path.join(temp_dir, "a", "b", "file.txt")
            _write(nested)
            os.utime(temp_dir, (1000, 1000))
            os.utime(os.path.join(temp_dir, "a"), (1000, 1000))
            os.utime(os.path.join(temp_dir, "a", "b"), (1000, 1000))
            os.utime(nested, (5000, 5000))
            self.assertEqual(get_latest_mtime(temp_dir), 5000)


if __name__ == "__main__":
    unittest.main()
