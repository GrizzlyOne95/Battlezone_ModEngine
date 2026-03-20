from dataclasses import dataclass


@dataclass
class TaskTransition:
    entered_busy: bool = False
    became_idle: bool = False


class TaskState:
    def __init__(self):
        self.task_count = 0
        self.download_active = False

    def start_task(self) -> TaskTransition:
        entered_busy = self.task_count == 0
        self.task_count += 1
        return TaskTransition(entered_busy=entered_busy, became_idle=False)

    def end_task(self) -> TaskTransition:
        self.task_count -= 1
        if self.task_count <= 0:
            self.task_count = 0
            return TaskTransition(entered_busy=False, became_idle=True)
        return TaskTransition(entered_busy=False, became_idle=False)

    def begin_download_batch(self) -> bool:
        if self.download_active:
            return False
        self.download_active = True
        return True

    def release_download_batch(self) -> None:
        self.download_active = False

    @property
    def has_active_tasks(self) -> bool:
        return self.task_count > 0


def calculate_batch_progress(item_percent: float, completed_count: int, total_items: int) -> dict:
    if total_items <= 0:
        return {
            "total_percent": 0.0,
            "label_text": "IDLE",
            "button_text": None,
            "complete": False,
        }

    clamped_item_percent = min(100.0, max(0.0, item_percent))
    total_percent = ((completed_count * 100.0) + clamped_item_percent) / total_items

    if completed_count == total_items:
        return {
            "total_percent": total_percent,
            "label_text": "100% - COMPLETE",
            "button_text": None,
            "complete": True,
        }

    return {
        "total_percent": total_percent,
        "label_text": f"{int(total_percent)}% (Item {completed_count + 1}/{total_items})",
        "button_text": f"DL {completed_count + 1}/{total_items} ({int(clamped_item_percent)}%)",
        "complete": False,
    }
