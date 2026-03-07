"""
Unit tests for Takeout module.

Tests cover JSON metadata parsing and JSON file finding with various
Google Takeout naming patterns.
"""

from __future__ import annotations

import json

from takeout_photos.takeout.json_finder import find_json_for_media
from takeout_photos.takeout.json_parser import parse_takeout_json


class TestJSONParser:
    """Test Google Takeout JSON metadata parsing."""

    def test_parse_valid_json_with_photo_taken_time(self, temp_dir):
        """Should extract photoTakenTime timestamp."""
        json_file = temp_dir / "photo.json"
        json_file.write_text(
            json.dumps(
                {
                    "photoTakenTime": {"timestamp": "1609459200"},
                    "geoData": {"latitude": 40.4168, "longitude": -3.7038},
                }
            )
        )

        result = parse_takeout_json(json_file)

        assert result["photo_taken_ts"] == 1609459200
        assert result["geo_lat"] == 40.4168
        assert result["geo_lon"] == -3.7038

    def test_parse_json_with_creation_time_fallback(self, temp_dir):
        """Should use creationTime if photoTakenTime not available."""
        json_file = temp_dir / "photo.json"
        json_file.write_text(
            json.dumps(
                {
                    "creationTime": {"timestamp": "1609459200"},
                    "geoData": {"latitude": 40.4168, "longitude": -3.7038},
                }
            )
        )

        result = parse_takeout_json(json_file)

        assert result["photo_taken_ts"] == 1609459200
        assert result["geo_lat"] == 40.4168
        assert result["geo_lon"] == -3.7038

    def test_parse_json_prefers_photo_taken_over_creation(self, temp_dir):
        """Should prefer photoTakenTime over creationTime."""
        json_file = temp_dir / "photo.json"
        json_file.write_text(
            json.dumps(
                {
                    "photoTakenTime": {"timestamp": "1609459200"},
                    "creationTime": {"timestamp": "1609545600"},
                }
            )
        )

        result = parse_takeout_json(json_file)

        assert result["photo_taken_ts"] == 1609459200  # photoTakenTime wins

    def test_parse_json_with_geo_data_exif(self, temp_dir):
        """Should extract geoDataExif when geoData not available."""
        json_file = temp_dir / "photo.json"
        json_file.write_text(
            json.dumps(
                {
                    "photoTakenTime": {"timestamp": "1609459200"},
                    "geoDataExif": {"latitude": 51.5074, "longitude": -0.1278},
                }
            )
        )

        result = parse_takeout_json(json_file)

        assert result["geo_lat"] == 51.5074
        assert result["geo_lon"] == -0.1278

    def test_parse_json_rejects_zero_coordinates(self, temp_dir):
        """Should not include (0.0, 0.0) coordinates."""
        json_file = temp_dir / "photo.json"
        json_file.write_text(
            json.dumps(
                {
                    "photoTakenTime": {"timestamp": "1609459200"},
                    "geoData": {"latitude": 0.0, "longitude": 0.0},
                }
            )
        )

        result = parse_takeout_json(json_file)

        assert "geo_lat" not in result
        assert "geo_lon" not in result

    def test_parse_json_missing_timestamp_fields(self, temp_dir):
        """Should handle missing timestamp fields gracefully."""
        json_file = temp_dir / "photo.json"
        json_file.write_text(json.dumps({"title": "My Photo"}))

        result = parse_takeout_json(json_file)

        assert "photo_taken_ts" not in result

    def test_parse_json_missing_geo_fields(self, temp_dir):
        """Should handle missing GPS fields gracefully."""
        json_file = temp_dir / "photo.json"
        json_file.write_text(json.dumps({"photoTakenTime": {"timestamp": "1609459200"}}))

        result = parse_takeout_json(json_file)

        assert "geo_lat" not in result
        assert "geo_lon" not in result

    def test_parse_invalid_json_returns_empty_dict(self, temp_dir):
        """Should return empty dict for invalid JSON."""
        json_file = temp_dir / "invalid.json"
        json_file.write_text("{ invalid json }")

        result = parse_takeout_json(json_file)

        assert result == {}

    def test_parse_missing_file_returns_empty_dict(self, temp_dir):
        """Should return empty dict for missing file."""
        json_file = temp_dir / "nonexistent.json"

        result = parse_takeout_json(json_file)

        assert result == {}

    def test_parse_json_invalid_timestamp_type(self, temp_dir):
        """Should handle non-numeric timestamp gracefully."""
        json_file = temp_dir / "photo.json"
        json_file.write_text(json.dumps({"photoTakenTime": {"timestamp": "not_a_number"}}))

        result = parse_takeout_json(json_file)

        assert "photo_taken_ts" not in result

    def test_parse_json_with_only_latitude(self, temp_dir):
        """Should not include GPS if only latitude present."""
        json_file = temp_dir / "photo.json"
        json_file.write_text(
            json.dumps(
                {
                    "photoTakenTime": {"timestamp": "1609459200"},
                    "geoData": {"latitude": 40.4168},
                }
            )
        )

        result = parse_takeout_json(json_file)

        assert "geo_lat" not in result
        assert "geo_lon" not in result


class TestJSONFinder:
    """Test JSON file finding with various naming patterns."""

    def test_find_json_standard_pattern(self, temp_dir):
        """Should find JSON with standard .json extension."""
        media_file = temp_dir / "photo.jpg"
        json_file = temp_dir / "photo.jpg.json"

        media_file.touch()
        json_file.touch()

        result = find_json_for_media(media_file)

        assert result == json_file

    def test_find_json_supplemental_metadata_pattern(self, temp_dir):
        """Should find JSON with supplemental-metadata pattern."""
        media_file = temp_dir / "photo.HEIC"
        json_file = temp_dir / "photo.HEIC.supplemental-metadata.json"

        media_file.touch()
        json_file.touch()

        result = find_json_for_media(media_file)

        assert result == json_file

    def test_find_json_numbered_suffix_before_extension(self, temp_dir):
        """Should find JSON with numbered suffix before extension: photo(1).jpg.json."""
        media_file = temp_dir / "photo.jpg"
        json_file = temp_dir / "photo(1).jpg.json"

        media_file.touch()
        json_file.touch()

        result = find_json_for_media(media_file)

        assert result == json_file

    def test_find_json_numbered_suffix_after_extension(self, temp_dir):
        """Should find JSON with numbered suffix after extension: photo.jpg(1).json."""
        media_file = temp_dir / "photo.jpg"
        json_file = temp_dir / "photo.jpg(1).json"

        media_file.touch()
        json_file.touch()

        result = find_json_for_media(media_file)

        assert result == json_file

    def test_find_json_truncated_filename(self, temp_dir):
        """Should find JSON for truncated long filenames (46+ chars)."""
        # Create a filename longer than 46 characters
        long_name = "a" * 50 + ".jpg"
        media_file = temp_dir / long_name

        # JSON file uses 46-char truncation
        truncated_name = "a" * 46
        json_file = temp_dir / f"{truncated_name}.jpg.json"

        media_file.touch()
        json_file.touch()

        result = find_json_for_media(media_file)

        assert result == json_file

    def test_find_json_returns_none_if_not_found(self, temp_dir):
        """Should return None if no JSON file found."""
        media_file = temp_dir / "photo.jpg"
        media_file.touch()

        result = find_json_for_media(media_file)

        assert result is None

    def test_find_json_global_search_in_google_photos(self, temp_dir):
        """Should search globally across ZIPs in Google Photos directories."""
        # Create extracted structure
        extracted_base = temp_dir / "extracted"
        zip1_photos = extracted_base / "takeout-001" / "Takeout" / "Google Photos" / "2024"
        zip2_photos = extracted_base / "takeout-002" / "Takeout" / "Google Photos" / "2023"
        zip1_photos.mkdir(parents=True)
        zip2_photos.mkdir(parents=True)

        # Media file in one ZIP, JSON in another
        media_file = zip1_photos / "photo.jpg"
        json_file = zip2_photos / "photo.jpg.json"

        media_file.touch()
        json_file.touch()

        result = find_json_for_media(media_file, extracted_base=extracted_base)

        assert result == json_file

    def test_find_json_local_search_first(self, temp_dir):
        """Should prefer local JSON over global search."""
        # Create extracted structure
        extracted_base = temp_dir / "extracted"
        local_dir = extracted_base / "takeout-001" / "Takeout" / "Google Photos"
        other_dir = extracted_base / "takeout-002" / "Takeout" / "Google Photos"
        local_dir.mkdir(parents=True)
        other_dir.mkdir(parents=True)

        # Create media file and both local and global JSON
        media_file = local_dir / "photo.jpg"
        local_json = local_dir / "photo.jpg.json"
        other_json = other_dir / "photo.jpg.json"

        media_file.touch()
        local_json.touch()
        other_json.touch()

        result = find_json_for_media(media_file, extracted_base=extracted_base)

        # Should find local JSON first
        assert result == local_json

    def test_find_json_without_extracted_base(self, temp_dir):
        """Should only search locally without extracted_base."""
        local_dir = temp_dir / "local"
        local_dir.mkdir()

        media_file = local_dir / "photo.jpg"
        json_file = local_dir / "photo.jpg.json"

        media_file.touch()
        json_file.touch()

        # No extracted_base provided
        result = find_json_for_media(media_file)

        assert result == json_file

    def test_find_json_skips_non_google_photos_dirs(self, temp_dir):
        """Should only search in Google Photos directories for global search."""
        extracted_base = temp_dir / "extracted"
        other_dir = extracted_base / "takeout-001" / "Takeout" / "Other"
        other_dir.mkdir(parents=True)

        media_file = temp_dir / "photo.jpg"
        json_file = other_dir / "photo.jpg.json"

        media_file.touch()
        json_file.touch()

        result = find_json_for_media(media_file, extracted_base=extracted_base)

        # Should not find JSON in non-Google-Photos directory
        assert result is None

    def test_find_json_multiple_patterns_in_order(self, temp_dir):
        """Should try patterns in order and return first match."""
        media_file = temp_dir / "photo.HEIC"

        # Create both standard and supplemental-metadata JSON
        standard_json = temp_dir / "photo.HEIC.json"
        supplemental_json = temp_dir / "photo.HEIC.supplemental-metadata.json"

        media_file.touch()
        standard_json.touch()
        supplemental_json.touch()

        result = find_json_for_media(media_file)

        # Should return first match (implementation dependent, but consistent)
        assert result in [standard_json, supplemental_json]


class TestTakeoutIntegration:
    """Integration tests for Takeout module."""

    def test_find_and_parse_json_workflow(self, temp_dir):
        """Should find and parse JSON in typical workflow."""
        media_file = temp_dir / "photo.jpg"
        json_file = temp_dir / "photo.jpg.json"

        media_file.touch()
        json_file.write_text(
            json.dumps(
                {
                    "photoTakenTime": {"timestamp": "1609459200"},
                    "geoData": {"latitude": 40.4168, "longitude": -3.7038},
                }
            )
        )

        # Find JSON
        found_json = find_json_for_media(media_file)
        assert found_json is not None

        # Parse JSON
        metadata = parse_takeout_json(found_json)
        assert metadata["photo_taken_ts"] == 1609459200
        assert metadata["geo_lat"] == 40.4168
        assert metadata["geo_lon"] == -3.7038

    def test_missing_json_returns_none_and_empty_dict(self, temp_dir):
        """Should handle missing JSON gracefully."""
        media_file = temp_dir / "photo.jpg"
        media_file.touch()

        # Find JSON (returns None)
        found_json = find_json_for_media(media_file)
        assert found_json is None

        # Can't parse None, but parse_takeout_json handles missing files
        nonexistent = temp_dir / "nonexistent.json"
        metadata = parse_takeout_json(nonexistent)
        assert metadata == {}
