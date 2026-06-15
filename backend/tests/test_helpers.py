import unittest

from backend.app.services.route_cache_service import (
    build_route_cache_metadata,
    extract_geometry,
    geometry_signature,
    normalize_countries,
)
from backend.app.services.trip_share_service import build_public_share_url, normalize_trip_visibility
from backend.app.utils.image_validation import detect_image_content_type


class TripShareServiceTests(unittest.TestCase):
    def test_normalize_trip_visibility_accepts_supported_values(self):
        self.assertEqual(normalize_trip_visibility(' Public '), 'public')
        self.assertEqual(normalize_trip_visibility('unlisted'), 'unlisted')
        self.assertEqual(normalize_trip_visibility(None), 'private')

    def test_normalize_trip_visibility_falls_back_for_invalid_values(self):
        self.assertEqual(normalize_trip_visibility('friends-only'), 'private')

    def test_build_public_share_url_returns_none_without_slug(self):
        self.assertIsNone(build_public_share_url(None))


class ImageValidationTests(unittest.TestCase):
    def test_detects_common_image_types(self):
        self.assertEqual(detect_image_content_type(b'\xff\xd8\xff\xdb' + b'x' * 20), 'image/jpeg')
        self.assertEqual(detect_image_content_type(b'\x89PNG\r\n\x1a\n' + b'x' * 20), 'image/png')
        self.assertEqual(detect_image_content_type(b'RIFF1234WEBP' + b'x' * 20), 'image/webp')

    def test_detects_heic_and_heif(self):
        self.assertEqual(detect_image_content_type(b'\x00\x00\x00\x18ftypheic' + b'x' * 20), 'image/heic')
        self.assertEqual(detect_image_content_type(b'\x00\x00\x00\x18ftypmif1' + b'x' * 20), 'image/heif')

    def test_returns_none_for_unknown_or_short_input(self):
        self.assertIsNone(detect_image_content_type(b'short'))
        self.assertIsNone(detect_image_content_type(b'\x00' * 20))


class RouteCacheServiceTests(unittest.TestCase):
    def test_extract_geometry_filters_invalid_points(self):
        payload = {'geometry': [[1, 2], ['3', '4'], ['bad'], None, [5, 'x']]}
        self.assertEqual(extract_geometry(payload), [[1.0, 2.0], [3.0, 4.0]])

    def test_normalize_countries_deduplicates_and_sorts(self):
        countries = [' japan ', 'France', 'japan', '  france  ', '', None]
        self.assertEqual(normalize_countries(countries), ['France', 'japan'])

    def test_geometry_signature_rounds_coordinates(self):
        geometry_a = [[1.123456, 2.654321], [3.333339, 4.444441]]
        geometry_b = [[1.1234561, 2.6543209], [3.3333391, 4.4444409]]
        self.assertEqual(geometry_signature(geometry_a), geometry_signature(geometry_b))

    def test_build_route_cache_metadata_summarizes_payload(self):
        payload = {
          'geometry': [[1, 2], [3, 4]],
          'countries': [' Switzerland ', 'switzerland', 'France'],
          'provider': ' local_geojson ',
        }
        metadata = build_route_cache_metadata(payload)
        self.assertEqual(metadata['provider'], 'local_geojson')
        self.assertEqual(metadata['point_count'], 2)
        self.assertEqual(metadata['countries'], ['France', 'Switzerland'])
        self.assertIsNotNone(metadata['geometry_signature'])


if __name__ == '__main__':
    unittest.main()
