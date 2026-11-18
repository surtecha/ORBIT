import unittest
from unittest.mock import Mock, patch

from backend.utils.spacetrack import AuthenticationError, SpaceTrackError, verify_session


class SessionVerificationTests(unittest.TestCase):
    def verify(self, payload):
        response = Mock(status_code=200)
        response.json.return_value = payload
        with patch('backend.utils.spacetrack.request', return_value=response):
            try:
                verify_session(Mock())
            finally:
                response.close.assert_called_once()

    def test_query_records_confirm_session(self):
        self.verify([{'NORAD_CAT_ID': '5'}])

    def test_login_failure_in_successful_http_response(self):
        with self.assertRaises(AuthenticationError):
            self.verify({'Login': 'Failed'})

    def test_unexpected_response_cannot_confirm_session(self):
        with self.assertRaises(SpaceTrackError):
            self.verify(['unexpected'])
