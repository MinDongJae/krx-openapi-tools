import copy
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from urllib.error import HTTPError, URLError
from urllib.request import Request
from unittest.mock import Mock, patch

from krx_openapi_tools import Client, KRXError, ValidationError, contract, normalize, validate
from krx_openapi_tools.__main__ import main
from krx_openapi_tools.core import _NoRedirect

ROOT = pathlib.Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / 'examples/synthetic-kospi.json').read_text(encoding='utf-8'))


class DataContracts(unittest.TestCase):
    def test_all_public_contracts_have_corresponding_schema(self):
        for market in ['kospi', 'kosdaq', 'konex']:
            with self.subTest(market=market):
                spec = contract(market)
                schema = json.loads((ROOT / 'schemas' / f'{market}-daily.schema.json').read_text(encoding='utf-8'))
                self.assertEqual(schema['properties']['OutBlock_1']['items']['required'], [f['name'] for f in spec['fields']])
                self.assertEqual(len(spec['fields']), 15)
                self.assertTrue(spec['source_url'].startswith('https://openapi.krx.co.kr/'))

    def test_valid_synthetic_response(self):
        self.assertTrue(validate(fixture(), 'kospi', expected_date='2026-01-02').valid)

    def test_error_object_is_not_empty_dataset(self):
        for value in [None, [], {'error': 'invalid key'}, {'OutBlock_1': {}}, {'OutBlock_1': None}]:
            with self.subTest(value=value):
                self.assertFalse(validate(value, 'kospi').valid)

    def test_empty_dataset_has_warning(self):
        report = validate({'OutBlock_1': []}, 'kospi')
        self.assertTrue(report.valid)
        self.assertEqual(report.issues[0].code, 'empty_dataset')

    def test_nonobject_row_fails(self):
        self.assertFalse(validate({'OutBlock_1': ['bad']}, 'kospi').valid)

    def test_missing_field_fails(self):
        data = fixture(); del data['OutBlock_1'][0]['ACC_TRDVAL']
        self.assertIn('missing_field', [x.code for x in validate(data, 'kospi').issues])

    def test_calendar_and_expected_date(self):
        for value in ['20260230', '20260103', '2026-01-02']:
            with self.subTest(value=value):
                data = fixture(); data['OutBlock_1'][0]['BAS_DD'] = value
                self.assertFalse(validate(data, 'kospi', expected_date='20260102').valid)

    def test_client_date_argument_is_validated_before_request(self):
        client = Client('synthetic-test-key'); client._opener = Mock()
        for day in ['20260230', '2026012', None, '20260102&other=1', '20260102\n']:
            with self.subTest(day=day):
                with self.assertRaises(ValueError): client.fetch('kospi', day)
        client._opener.open.assert_not_called()

    def test_identifier_letters_and_leading_zero_survive(self):
        for value in ['0043Y0', '000001']:
            data = fixture(); data['OutBlock_1'][0]['ISU_CD'] = value
            self.assertEqual(normalize(data, 'kospi')[0]['ISU_CD'], value)

    def test_numeric_identifier_and_invalid_length_fail(self):
        for value in [1234, '1234', '0043y0', '0000012']:
            with self.subTest(value=value):
                data = fixture(); data['OutBlock_1'][0]['ISU_CD'] = value
                self.assertFalse(validate(data, 'kospi').valid)

    def test_exact_precision_zero_and_missing(self):
        data = normalize(fixture(), 'kospi')[0]
        self.assertEqual(data['MKTCAP'], '9007199254740993')
        self.assertEqual(data['ACC_TRDVOL'], '0')
        self.assertIsNone(data['ACC_TRDVAL'])
        self.assertEqual(data['SECT_TP_NM'], '-')
        self.assertEqual(data['FLUC_RT'], '-0.10')
        self.assertEqual(data['BAS_DD'], '2026-01-02')

    def test_invalid_numeric_values_are_rejected(self):
        for value in ['1,23', '1,,000', 'NaN', 'Infinity', '1e6', '', None, 100.0, True]:
            with self.subTest(value=value):
                data = fixture(); data['OutBlock_1'][0]['TDD_CLSPRC'] = value
                self.assertFalse(validate(data, 'kospi').valid)

    def test_negative_quantity_and_signed_change(self):
        data = fixture(); data['OutBlock_1'][0]['ACC_TRDVOL'] = '-1'
        self.assertFalse(validate(data, 'kospi').valid)
        self.assertTrue(validate(fixture(), 'kospi').valid)

    def test_additional_fields_are_retained_and_warned(self):
        data = fixture(); data['OutBlock_1'][0]['FUTURE_FIELD'] = 'value'
        report = validate(data, 'kospi')
        self.assertTrue(report.valid)
        self.assertEqual(report.issues[0].code, 'unknown_field')
        self.assertEqual(normalize(data, 'kospi')[0]['FUTURE_FIELD'], 'value')

    def test_duplicates_warn(self):
        data = fixture(); data['OutBlock_1'].append(copy.deepcopy(data['OutBlock_1'][0]))
        self.assertIn('duplicate_record', [x.code for x in validate(data, 'kospi').issues])

    def test_normalization_does_not_mutate_raw_data(self):
        data = fixture(); before = copy.deepcopy(data)
        normalize(data, 'kospi')
        self.assertEqual(data, before)

    def test_invalid_data_cannot_be_normalized(self):
        with self.assertRaises(ValidationError): normalize({'error': 'bad'}, 'kospi')

    def test_contract_copy_and_invalid_market(self):
        data = contract('kospi'); data['fields'].clear()
        self.assertEqual(len(contract('kospi')['fields']), 15)
        with self.assertRaises(ValueError): contract('../file')


class Response:
    status = 200
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size): return self.body[:size]


class Transport(unittest.TestCase):
    def client(self, body):
        client = Client('synthetic-test-key', timeout=3)
        client._opener = Mock()
        client._opener.open.return_value = Response(body)
        return client

    def test_request_header_endpoint_date_and_provenance(self):
        client = self.client(json.dumps(fixture()).encode())
        result = client.fetch('kospi', '2026-01-02')
        request = client._opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd?basDd=20260102')
        self.assertEqual(request.get_header('Auth_key'), 'synthetic-test-key')
        self.assertNotIn('synthetic-test-key', request.full_url)
        self.assertTrue(result['validation']['valid'])
        self.assertNotIn('synthetic-test-key', json.dumps(result))
        self.assertEqual(client._opener.open.call_args.kwargs['timeout'], 3)

    def test_key_and_timeout_validation(self):
        for key in ['', None, 'x\r\ny']:
            with self.assertRaises(ValueError): Client(key)
        for timeout in [0, -1, float('nan'), float('inf'), True]:
            with self.assertRaises(ValueError): Client('test', timeout=timeout)

    def test_http_error_omits_sensitive_details(self):
        client = self.client(b'')
        client._opener.open.side_effect = HTTPError('https://bad/?key=secret', 403, 'secret', {}, None)
        with self.assertRaises(KRXError) as caught: client.fetch('kospi', '20260102')
        self.assertIn('403', str(caught.exception))
        self.assertNotIn('secret', str(caught.exception))

    def test_network_error_omits_sensitive_details(self):
        client = self.client(b'')
        client._opener.open.side_effect = URLError('secret')
        with self.assertRaises(KRXError) as caught: client.fetch('kospi', '20260102')
        self.assertNotIn('secret', str(caught.exception))

    def test_redirect_refused(self):
        with self.assertRaises(KRXError):
            _NoRedirect().redirect_request(Request('https://data-dbg.krx.co.kr/'), None, 302, '', {}, 'https://untrusted.invalid/')

    def test_response_size_limit(self):
        client = self.client(b'0123456789')
        with patch('krx_openapi_tools.core.MAX_RESPONSE_BYTES', 8):
            with self.assertRaisesRegex(KRXError, 'limit'): client.fetch('kospi', '20260102')

    def test_malformed_utf8_html_and_error_json(self):
        for body in [b'\xff', b'<html>error</html>', b'{"error":"invalid"}']:
            with self.subTest(body=body):
                with self.assertRaises(KRXError): self.client(body).fetch('kospi', '20260102')

    def test_wrong_date_from_server_rejected(self):
        data = fixture(); data['OutBlock_1'][0]['BAS_DD'] = '20260103'
        with self.assertRaises(ValidationError): self.client(json.dumps(data).encode()).fetch('kospi', '20260102')


class CommandLine(unittest.TestCase):
    def test_offline_example_and_bad_file_exit_codes(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(['validate', '--market', 'kospi', str(ROOT/'examples/synthetic-kospi.json'), '--normalized']), 0)
            self.assertEqual(main(['validate', '--market', 'kospi', str(ROOT/'missing.json')]), 2)

    def test_invalid_payload_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp)/'error.json'; path.write_text('{"error":"bad"}', encoding='utf-8')
            with redirect_stdout(io.StringIO()): self.assertEqual(main(['validate','--market','kospi',str(path)]),1)

    def test_existing_output_is_not_overwritten_or_fetched(self):
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)/'keep.json'; path.write_text('keep',encoding='utf-8')
            with patch('krx_openapi_tools.__main__.Client') as client, redirect_stderr(io.StringIO()):
                self.assertEqual(main(['fetch','--market','kospi','--date','20260102','--output',str(path)]),2)
                client.assert_not_called()
            self.assertEqual(path.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
