"""The opt-in synthetic runner must not open a DB outside its test target."""
import os
import unittest
from unittest.mock import patch

from test_api_worker_integration import CheckFailure, validate_database_url


class DatabaseGuardTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.allowed = 'postgresql://storage_lab_console@postgres:5432/osdmap_synthetic_unit'

    def deny(self, value):
        with self.assertRaisesRegex(CheckFailure, 'ISOLATED_SYNTHETIC_DATABASE_TARGET_REQUIRED'):
            validate_database_url(value)

    def test_explicit_isolated_target_is_accepted(self):
        validate_database_url(self.allowed)
        validate_database_url('postgres://storage_lab_console@postgres/osdmap_synthetic_unit')

    def test_query_host_override_is_rejected(self):
        self.deny(self.allowed + '?host=production.example')

    def test_query_database_override_is_rejected(self):
        self.deny(self.allowed + '?dbname=production')

    def test_service_options_and_encoded_query_overrides_are_rejected(self):
        for query in ('service=prod', 'options=-csearch_path=private', 'hostaddr=10.1.2.3',
                      'h%6fst=production.example'):
            with self.subTest(query=query):
                self.deny(self.allowed + '?' + query)

    def test_fragment_is_rejected(self):
        self.deny(self.allowed + '#service=prod')

    def test_other_or_multiple_hosts_are_rejected(self):
        for host in ('production.example', 'postgres,production.example', '%70ostgres', 'postgres.'):
            with self.subTest(host=host):
                self.deny(self.allowed.replace('@postgres:', '@' + host + ':'))

    def test_non_synthetic_or_path_injection_databases_are_rejected(self):
        for database in ('storage_lab_console', 'osdmap_synthetic_test%2Fproduction',
                         'osdmap_synthetic_test%3Fhost%3Dproduction.example', 'osdmap_synthetic_test/other'):
            with self.subTest(database=database):
                self.deny(self.allowed.replace('osdmap_synthetic_unit', database))

    def test_other_user_port_and_scheme_are_rejected(self):
        for value in (self.allowed.replace('storage_lab_console', 'production_user'),
                      self.allowed.replace(':5432/', ':5433/'),
                      self.allowed.replace(':5432/', ':invalid/'),
                      self.allowed.replace('postgresql:', 'http:')):
            with self.subTest(target=value):
                self.deny(value)

    def test_implicit_libpq_environment_overrides_are_rejected(self):
        for key in ('PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGDATABASE', 'PGUSER',
                    'PGSERVICE', 'PGSERVICEFILE', 'PGOPTIONS'):
            with self.subTest(variable=key), patch.dict(os.environ, {key: 'unexpected'}):
                self.deny(self.allowed)


if __name__ == '__main__':
    unittest.main()
