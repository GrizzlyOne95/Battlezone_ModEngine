import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape


MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


@dataclass(frozen=True)
class WorkshopMetadata:
    title: str | None
    appid: str | None
    thumbnail_url: str | None
    remote_date_text: str | None


def extract_required_item_ids(html: str) -> list[str]:
    start_match = re.search(r'<div[^>]*class="requiredItemsContainer"[^>]*>', html)
    if not start_match:
        return []

    start_idx = start_match.end()
    balance = 1
    idx = start_idx

    while balance > 0 and idx < len(html):
        next_open = html.find("<div", idx)
        next_close = html.find("</div>", idx)

        if next_close == -1:
            break

        if next_open != -1 and next_open < next_close:
            balance += 1
            idx = next_open + 4
        else:
            balance -= 1
            idx = next_close + 6

    block = html[start_idx:idx]
    return sorted(set(re.findall(r"id=(\d+)", block)))


def parse_workshop_metadata(html: str) -> WorkshopMetadata:
    title_match = re.search(r'<div class="workshopItemTitle">(.*?)</div>', html, re.DOTALL)
    app_match = re.search(r"steamcommunity\.com/app/(\d+)", html)
    thumb_match = re.search(r'id="ActualImage"\s+src="([^"]+)"', html)
    if not thumb_match:
        thumb_match = re.search(r'<link rel="image_src" href="([^"]+)">', html)

    date_match = re.search(r'<(?:div|span) class="detailsStatRight">([^<]+)</(?:div|span)>', html)
    title = clean_html_text(title_match.group(1)) if title_match else None

    return WorkshopMetadata(
        title=title,
        appid=app_match.group(1) if app_match else None,
        thumbnail_url=thumb_match.group(1) if thumb_match else None,
        remote_date_text=clean_html_text(date_match.group(1)) if date_match else None,
    )


def parse_workshop_datetime(date_text: str | None, now: datetime | None = None) -> datetime | None:
    if not date_text:
        return None

    clean_str = clean_html_text(date_text).replace("@", "").strip()
    if not clean_str:
        return None

    parts = clean_str.replace(",", "").split()
    if len(parts) < 3:
        return None

    try:
        day = int(parts[0])
        month = MONTHS.get(parts[1])
        if month is None:
            return None

        current_time = now or datetime.now()
        if ":" in parts[2]:
            year = current_time.year
            time_str = parts[2]
        else:
            if len(parts) < 4:
                return None
            year = int(parts[2])
            time_str = parts[3]

        dt_str = f"{year}-{month:02d}-{day:02d} {time_str.lower()}"
        return datetime.strptime(dt_str, "%Y-%m-%d %I:%M%p")
    except (TypeError, ValueError, IndexError):
        return None


def is_remote_newer(remote_date_text: str | None, local_ts: float, now: datetime | None = None) -> bool:
    remote_dt = parse_workshop_datetime(remote_date_text, now=now)
    if not remote_dt:
        return False
    local_dt = datetime.fromtimestamp(local_ts)
    return remote_dt.date() > local_dt.date()


def clean_html_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(unescape(value).split())
