import contextlib
import io
import threading
import unittest

from task_utils import TaskState, TtlCache, UiDispatcher, calculate_batch_progress


class TaskUtilsTests(unittest.TestCase):
    def test_task_state_transitions(self):
        state = TaskState()

        first = state.start_task()
        self.assertTrue(first.entered_busy)
        self.assertFalse(first.became_idle)
        self.assertTrue(state.has_active_tasks)

        second = state.start_task()
        self.assertFalse(second.entered_busy)
        self.assertEqual(state.task_count, 2)

        still_busy = state.end_task()
        self.assertFalse(still_busy.became_idle)
        self.assertEqual(state.task_count, 1)

        idle = state.end_task()
        self.assertTrue(idle.became_idle)
        self.assertFalse(state.has_active_tasks)
        self.assertEqual(state.task_count, 0)

    def test_download_batch_gate(self):
        state = TaskState()
        self.assertTrue(state.begin_download_batch())
        self.assertFalse(state.begin_download_batch())
        state.release_download_batch()
        self.assertTrue(state.begin_download_batch())

    def test_calculate_batch_progress_in_progress(self):
        progress = calculate_batch_progress(25.0, 1, 4)
        self.assertEqual(progress["label_text"], "31% (Item 2/4)")
        self.assertEqual(progress["button_text"], "DL 2/4 (25%)")
        self.assertFalse(progress["complete"])

    def test_calculate_batch_progress_complete(self):
        progress = calculate_batch_progress(100.0, 3, 3)
        self.assertEqual(progress["label_text"], "100% - COMPLETE")
        self.assertIsNone(progress["button_text"])
        self.assertTrue(progress["complete"])

    def test_calculate_batch_progress_handles_empty_total(self):
        progress = calculate_batch_progress(50.0, 0, 0)
        self.assertEqual(progress["label_text"], "IDLE")
        self.assertEqual(progress["total_percent"], 0.0)


    def test_ui_dispatcher_runs_callbacks_in_order_and_survives_errors(self):
        dispatcher = UiDispatcher()
        seen = []
        dispatcher.post(lambda: seen.append(1))
        dispatcher.post(lambda: 1 / 0)
        dispatcher.post(lambda: seen.append(2))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(dispatcher.drain(), 3)
        self.assertEqual(seen, [1, 2])
        self.assertEqual(dispatcher.drain(), 0)

    def test_ui_dispatcher_accepts_posts_from_other_threads(self):
        dispatcher = UiDispatcher()
        seen = []
        workers = [threading.Thread(target=dispatcher.post, args=(lambda i=i: seen.append(i),)) for i in range(20)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        dispatcher.drain()
        self.assertEqual(sorted(seen), list(range(20)))

    def test_ttl_cache_expires_and_discards(self):
        now = [0.0]
        cache = TtlCache(10, clock=lambda: now[0])
        cache.set("a", 1)
        self.assertEqual(cache.get("a"), 1)
        now[0] = 11
        self.assertIsNone(cache.get("a"))
        cache.set("b", 2)
        cache.discard("b")
        self.assertIsNone(cache.get("b"))


if __name__ == "__main__":
    unittest.main()
