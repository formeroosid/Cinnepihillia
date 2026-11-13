# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

"""Movie folder parsing and Plex feature naming."""
import unittest

from movies.movie_pipeline import (feature_basename, get_movie_edition,
                                   get_movie_info, split_edition)


class MovieNamingTests(unittest.TestCase):
    def test_plain_folder(self):
        root = "/m/Fight Club (1999)"
        self.assertEqual(get_movie_info(root), ("Fight Club", "1999"))
        self.assertIsNone(get_movie_edition(root))
        self.assertEqual(feature_basename("Fight Club", "1999"), "Fight Club (1999)")

    def test_edition_folder(self):
        root = "/m/Star Trek - The Motion Picture (1979) {edition-Director's Edition}/"
        self.assertEqual(get_movie_info(root), ("Star Trek - The Motion Picture", "1979"))
        self.assertEqual(get_movie_edition(root), "Director's Edition")
        self.assertEqual(
            feature_basename("Star Trek - The Motion Picture", "1979", "Director's Edition"),
            "Star Trek - The Motion Picture (1979) {edition-Director's Edition}")

    def test_extra_spaces_and_case(self):
        root = "/m/Weird: The Al Yankovic Story  (2022)  {Edition-Extended}"
        self.assertEqual(get_movie_info(root), ("Weird: The Al Yankovic Story", "2022"))
        self.assertEqual(get_movie_edition(root), "Extended")

    def test_no_year(self):
        self.assertEqual(get_movie_info("/m/Untitled"), ("Untitled", ""))
        self.assertEqual(feature_basename("Untitled", ""), "Untitled")
        self.assertEqual(feature_basename("Untitled", "", "Cut"), "Untitled {edition-Cut}")

    def test_non_edition_braces_kept(self):
        self.assertEqual(split_edition("Movie (2000) {tmdb-123}"), ("Movie (2000) {tmdb-123}", None))


if __name__ == "__main__":
    unittest.main()
