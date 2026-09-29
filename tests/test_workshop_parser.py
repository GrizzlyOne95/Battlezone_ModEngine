import unittest
from datetime import datetime

from workshop_parser import (
    WorkshopMetadata,
    classify_workshop_app,
    extract_required_item_ids,
    is_remote_newer,
    parse_workshop_datetime,
    parse_workshop_metadata,
)


SAMPLE_HTML = """
<html>
  <head>
    <link rel="image_src" href="https://cdn.example.com/fallback.png">
  </head>
  <body>
    <a href="https://steamcommunity.com/app/301650/workshop/">Workshop</a>
    <div class="workshopItemTitle">Campaign &amp; Reimagined</div>
    <img id="ActualImage" src="https://cdn.example.com/actual.png">
    <div class="detailsStatRight">23 Oct, 2016 @ 3:47pm</div>
    <div class="requiredItemsContainer">
      <div><a href="?id=111">One</a></div>
      <div>
        <div><a href="?id=222">Two</a></div>
        <div><a href="?id=111">Duplicate</a></div>
      </div>
    </div>
  </body>
</html>
"""


# Mirrors the Workshop page layout: the stats column lists File Size, Posted
# and Updated, in that order.
STATS_HTML = """
<div class="detailsStatsContainerRight">
    <div class="detailsStatRight">12.345 MB</div>
    <div class="detailsStatRight">23 Oct, 2016 @ 3:47pm</div>
    <div class="detailsStatRight">4 Mar, 2019 @ 11:02am</div>
</div>
"""

POSTED_ONLY_HTML = """
<div class="detailsStatsContainerRight">
    <div class="detailsStatRight">1.2 MB</div>
    <div class="detailsStatRight">23 Oct, 2016 @ 3:47pm</div>
</div>
"""


class WorkshopParserTests(unittest.TestCase):
    def test_remote_date_uses_updated_not_file_size(self):
        self.assertEqual(parse_workshop_metadata(STATS_HTML).remote_date_text, "4 Mar, 2019 @ 11:02am")

    def test_remote_date_falls_back_to_posted(self):
        self.assertEqual(parse_workshop_metadata(POSTED_ONLY_HTML).remote_date_text, "23 Oct, 2016 @ 3:47pm")

    def test_update_detection_with_realistic_stats(self):
        local_ts = datetime(2017, 1, 1, 12, 0).timestamp()
        remote = parse_workshop_metadata(STATS_HTML).remote_date_text
        self.assertTrue(is_remote_newer(remote, local_ts))

    def test_classify_workshop_app(self):
        def meta(appid):
            return WorkshopMetadata(title=None, appid=appid, thumbnail_url=None, remote_date_text=None)

        self.assertEqual(classify_workshop_app(meta("301650"), "301650"), "valid")
        self.assertEqual(classify_workshop_app(meta("624970"), "301650"), "wrong_game")
        self.assertEqual(classify_workshop_app(meta(None), "301650"), "unknown")

    def test_extract_required_item_ids_deduplicates_and_sorts(self):
        self.assertEqual(extract_required_item_ids(SAMPLE_HTML), ["111", "222"])

    def test_parse_workshop_metadata_extracts_expected_fields(self):
        metadata = parse_workshop_metadata(SAMPLE_HTML)
        self.assertEqual(
            metadata,
            WorkshopMetadata(
                title="Campaign & Reimagined",
                appid="301650",
                thumbnail_url="https://cdn.example.com/actual.png",
                remote_date_text="23 Oct, 2016 @ 3:47pm",
            ),
        )

    def test_parse_workshop_datetime_handles_explicit_year(self):
        parsed = parse_workshop_datetime("23 Oct, 2016 @ 3:47pm")
        self.assertEqual(parsed, datetime(2016, 10, 23, 15, 47))

    def test_parse_workshop_datetime_handles_missing_year(self):
        parsed = parse_workshop_datetime(
            "23 Oct @ 3:47pm",
            now=datetime(2026, 3, 20, 9, 0),
        )
        self.assertEqual(parsed, datetime(2026, 10, 23, 15, 47))

    def test_is_remote_newer_compares_dates(self):
        local_ts = datetime(2016, 10, 22, 11, 0).timestamp()
        self.assertTrue(is_remote_newer("23 Oct, 2016 @ 3:47pm", local_ts))
        self.assertFalse(is_remote_newer("22 Oct, 2016 @ 3:47pm", local_ts))

    def test_parse_workshop_metadata_handles_missing_fields(self):
        metadata = parse_workshop_metadata("<html><body>No workshop markup</body></html>")
        self.assertEqual(
            metadata,
            WorkshopMetadata(
                title=None,
                appid=None,
                thumbnail_url=None,
                remote_date_text=None,
            ),
        )


if __name__ == "__main__":
    unittest.main()
