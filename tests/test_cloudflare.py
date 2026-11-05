import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import cloudflare_data as data
import cloudflare_oauth as auth


class CloudflareTests(unittest.TestCase):
    def setUp(self):
        fixture = [('example.com','a'*32), ('example.net','b'*32), ('example.org','c'*32), ('example.test','d'*32)]
        patcher = patch.object(data, 'SITES', fixture); patcher.start(); self.addCleanup(patcher.stop)
        account = patch.object(data, 'ACCOUNT', '0'*32); account.start(); self.addCleanup(account.stop)

    def fixture(self, totals=True):
        return {'period': {'start':'2026-11-04T05:00:00Z','end':'2026-11-05T05:00:00Z'},
                'sites':[{'name':'example.com','id':data.SITES[0][1], 'data':{
                    'totals':[{'sum':{'requests':10,'cachedRequests':3,'bytes':2000,
                        'responseStatusMap':[{'edgeResponseStatus':404,'requests':4},{'edgeResponseStatus':502,'requests':1}]},
                        'uniq':{'uniques':2}}] if totals else [],
                    'hourly':[{'dimensions':{'datetime':'2026-11-04T06:00:00Z'},'sum':{'requests':10}}]}}]}

    def test_aggregates_and_gaps(self):
        result=data.normalize(self.fixture(),'example.com')
        self.assertEqual((result['requests'],result['cache_percent'],result['server_errors'],result['client_errors'],result['not_found']), (10,30,1,4,4))
        self.assertEqual(len(result['hourly']),24)
        self.assertEqual(result['hourly'][:3],[0,10,0])

    def test_missing_is_not_zero(self):
        self.assertIsNone(data.normalize(None,'example.com'))
        self.assertIsNone(data.normalize(self.fixture(),'example.test'))
        result=data.normalize(self.fixture(False),'example.com')
        self.assertEqual(result['requests'],0)
        self.assertIsNone(result['cache_percent'])
        incomplete=self.fixture();del incomplete['sites'][0]['data']['totals']
        self.assertIsNone(data.normalize(incomplete,'example.com'))
        self.assertIsNone(data.normalize({'sites':[None]},'example.com'))

    def test_rolling_window_and_allowed_dashboard(self):
        window=data.period(datetime(2026,11,5,5,44,tzinfo=timezone.utc))
        self.assertEqual(window,{'start':'2026-11-04T05:44:00+00:00','end':'2026-11-05T05:44:00+00:00'})
        with self.assertRaises(ValueError):data.dashboard('other-site.test')

    def test_sse_ignores_notices_and_matches_response_id(self):
        body='event: message\r\ndata: {"method":"notice"}\r\n\r\nevent: message\r\ndata: {"id":2,"result":{"content":[]}}\r\n\r\n'
        self.assertEqual(auth.decode_response(body,'text/event-stream',2)['id'],2)

    def test_token_file_is_private_and_refresh_retains_refresh_token(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(auth,'TOKEN_FILE',Path(folder)/'token.json'):
            auth.save_tokens({'client_id':'test','access_token':'not-a-real-token','expires_at':9999999999})
            self.assertEqual(auth.TOKEN_FILE.stat().st_mode & 0o777,0o600)
            self.assertTrue(auth.connected())
        with patch.object(auth.time,'time',return_value=100):
            value=auth.merge_tokens({'access_token':'new','expires_in':60},{'client_id':'test','refresh_token':'keep'})
        self.assertEqual(value['refresh_token'],'keep')
        self.assertEqual(value['expires_at'],160)

    def test_failed_fetch_does_not_replace_cache(self):
        with patch.object(auth,'execute',return_value={'errors':[{'message':'denied'}]}),patch.object(data,'write_json') as write:
            with self.assertRaises(RuntimeError):data.fetch()
            write.assert_not_called()

    def test_untrusted_endpoint_is_rejected_before_network(self):
        with patch.object(auth,'urlopen') as network:
            with self.assertRaises(auth.ConnectionError):auth.request('https://example.com/token')
            network.assert_not_called()

    def test_account_hosts_stay_separate_and_current_hour_is_kept(self):
        account={'totals':[{'count':10,'dimensions':{'clientRequestHTTPHost':'example.com'},'sum':{'edgeResponseBytes':500}},
                           {'count':4,'dimensions':{'clientRequestHTTPHost':'www.example.com'},'sum':{'edgeResponseBytes':100}}],
                 'history':[{'count':3,'dimensions':{'clientRequestHTTPHost':'example.com','datetimeFifteenMinutes':'2026-11-05T05:30:00Z'}}],
                 'breakdown':[{'count':2,'dimensions':{'clientRequestHTTPHost':'example.com','cacheStatus':'hit','edgeResponseStatus':200}},
                              {'count':1,'dimensions':{'clientRequestHTTPHost':'example.com','cacheStatus':'none','edgeResponseStatus':502}}]}
        window=data.period(datetime(2026,11,5,5,44,tzinfo=timezone.utc))
        record=data.account_record({'data':{'viewer':{'accounts':[account]}}},window,12345)
        site=data.normalize(record,'example.com')
        self.assertEqual((site['requests'],site['www_requests'],site['cache_percent'],site['server_errors']),(10,4,20,1))
        self.assertIsNone(site['unique_ips'])
        self.assertEqual(site['hourly'][-1],3)
        self.assertEqual(len(site['hourly']),97)
        self.assertEqual(data.normalize(record,'example.net')['requests'],0)
        with self.assertRaises(RuntimeError):data.account_record({'data':{'viewer':{'accounts':[{'totals':[]}]}}},window)

    def test_read_only_mcp_protocol(self):
        seen=[]
        def request(url,payload=None,headers=None,**kwargs):
            seen.append(payload)
            if payload['method']=='initialize':return {'result':{'protocolVersion':'2025-03-26'}},{'Mcp-Session-Id':'test-session'}
            if payload['method']=='notifications/initialized':return {},{}
            return {'result':{'content':[{'type':'text','text':json.dumps({'data':{'viewer':{'zones':[]}}})}]}},{}
        with patch.object(auth,'access_token',return_value='test-only'),patch.object(auth,'request',side_effect=request):
            value=auth.execute('async () => {}',data.ACCOUNT)
        self.assertIn('data',value)
        self.assertEqual([item['method'] for item in seen],['initialize','notifications/initialized','tools/call'])
        self.assertEqual(seen[-1]['params']['name'],'execute')


if __name__=='__main__':unittest.main()
