import unittest
from datetime import datetime

from workshop_parser import (
    WorkshopMetadata,
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


class WorkshopParserTests(unittest.TestCase):
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
