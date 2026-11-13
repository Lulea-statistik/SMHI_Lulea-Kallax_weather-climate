#!/usr/bin/env python3
"""Regression checks for combining archived and recent SMHI snow observations."""
import unittest
from datetime import date
from fetch_snowmap import merge_period_observations, season_name

class SnowPeriodMergeTest(unittest.TestCase):
    def test_latest_months_replaces_overlapping_archive_day(self):
        a, b, c = date(2026, 7, 31), date(2026, 8, 1), date(2026, 11, 12)
        merged = merge_period_observations({
            "corrected-archive": [(a, 0.0), (b, 2.0)],
            "latest-months": [(b, 3.0), (c, 12.0)],
        })
        self.assertEqual(merged, [(a, 0.0), (b, 3.0), (c, 12.0)])

    def test_archive_survives_unavailable_recent_period(self):
        a = date(2026, 8, 1)
        self.assertEqual(merge_period_observations({"corrected-archive": [(a, 0.0)]}), [(a, 0.0)])

    def test_no_archive_still_yields_new_period(self):
        a = date(2026, 11, 12)
        self.assertEqual(merge_period_observations({"latest-months": [(a, 1.0)]}), [(a, 1.0)])

    def test_november_in_current_snow_season(self):
        self.assertEqual(season_name(date(2026, 11, 12)), "2026-27")

if __name__ == "__main__":
    unittest.main()
