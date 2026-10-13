import unittest
from unittest.mock import patch

from app import app
from backend import auth


class AuthTests(unittest.TestCase):
    def test_public_config_uses_only_public_auth_key(self):
        with patch.dict('os.environ', {'SUPABASE_URL':'https://example.supabase.co','SUPABASE_ANON_KEY':'public-key'}, clear=False):
            self.assertEqual(auth.public_config(),('https://example.supabase.co','public-key'))
        with patch.dict('os.environ', {'SUPABASE_URL':'http://example.supabase.co','SUPABASE_ANON_KEY':'public-key'}, clear=False):
            with self.assertRaises(auth.AuthConfigurationError):auth.public_config()

    def test_data_api_requires_a_verified_session(self):
        app.config['TESTING']=False
        client=app.test_client()
        self.assertEqual(client.get('/api/state').status_code,401)
        self.assertEqual(client.post('/api/vehicles',json={'name':'No session'}).status_code,401)

    def test_user_lookup_returns_only_supabase_identity(self):
        with patch('backend.auth.call',return_value={'id':'11111111-1111-4111-8111-111111111111','email':'owner@example.com','email_confirmed_at':'2026-01-01T00:00:00Z','user_metadata':{'secret':'ignored'}}):
            self.assertEqual(auth.current_user('valid-token'),{'id':'11111111-1111-4111-8111-111111111111','email':'owner@example.com','email_verified':True})
        with patch('backend.auth.call',side_effect=auth.AuthError('expired',401)):
            self.assertIsNone(auth.current_user('expired-token'))


if __name__=='__main__':unittest.main()
