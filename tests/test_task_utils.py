import unittest

from task_utils import TaskState, calculate_batch_progress


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


if __name__ == "__main__":
    unittest.main()
