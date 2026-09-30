import os
import unittest
from unittest.mock import patch
import psycopg
from app import app
from backend.db import connection_info, ConfigurationError
from backend.diagnostics import database_problem

class DatabaseConfigurationTests(unittest.TestCase):
    def test_missing_configuration_is_actionable(self):
        with patch.dict(os.environ, {}, clear=True):
            response=app.test_client().get('/api/health')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.get_json()['code'],'database_configuration')
        self.assertIn('Redeploy',response.get_json()['error'])

    def test_aliases_and_explicit_priority(self):
        url='postgresql://user:secret@localhost:5432/fuel_test'
        for name in ('DATABASE_URL','SUPABASE_DB_URL','POSTGRES_URL'):
            with patch.dict(os.environ,{name:url},clear=True):
                self.assertEqual(connection_info()['dbname'],'fuel_test')
        with patch.dict(os.environ,{'DATABASE_URL':'https://wrong.example','POSTGRES_URL':url},clear=True):
            with self.assertRaises(ConfigurationError):connection_info()

    def test_bad_urls_never_echo_secret(self):
        for value in ('https://example.supabase.co/secret-value','postgresql://user:secret-value@','postgresql://user:secret-value@POOLER_HOST/db','"postgresql://user:secret-value@host/db"'):
            with self.assertRaises(ConfigurationError) as error:connection_info(value)
            self.assertNotIn('secret-value',str(error.exception))

    def test_database_errors_are_safe_and_distinct(self):
        for error,code in ((psycopg.errors.UndefinedTable('secret'),'database_schema'),
                (psycopg.errors.InsufficientPrivilege('secret'),'database_permissions'),
                (psycopg.errors.InvalidPassword('secret'),'database_authentication'),
                (psycopg.OperationalError('secret'),'database_connection')):
            actual,message=database_problem(error)
            self.assertEqual(actual,code)
            self.assertNotIn('secret',message)

    def test_invalid_timeout_returns_configuration_error(self):
        from backend.config import integer_setting
        with patch.dict(os.environ,DB_CONNECT_TIMEOUT_SECONDS='abc'):
            with self.assertRaises(ConfigurationError):integer_setting('DB_CONNECT_TIMEOUT_SECONDS',5)

if __name__=='__main__':unittest.main()
