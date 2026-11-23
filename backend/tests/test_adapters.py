import os
import unittest
import json
import requests
from unittest.mock import patch, Mock, MagicMock
from app.services import market_data, news, llm, band_bridge

class AdapterTests(unittest.TestCase):
    @patch.dict(os.environ, {'BAND_AGENT_API_KEY':'','BAND_CHAT_ID':'room',
                             'BAND_AGENT_KEYS':'{"analyst":"unit-test-key"}',
                             'BAND_AGENT_PEERS':'{}'}, clear=False)
    @patch('app.services.band_bridge.requests.get', side_effect=requests.exceptions.ProxyError('sensitive proxy detail'))
    def test_band_identity_failure_reports_safe_exception_and_elapsed_time(self, get):
        result=band_bridge.validate_identity('analyst')
        self.assertEqual(result['state'],'network_failure')
        self.assertEqual(result['exception_class'],'ProxyError')
        self.assertEqual(result['network_error_kind'],'proxy_error')
        self.assertEqual(result['error_description'],'Proxy connection or negotiation failed.')
        self.assertGreaterEqual(result['elapsed_ms'],0)
        self.assertIsNone(result['http_status'])
        self.assertNotIn('sensitive proxy detail',json.dumps(result))
        self.assertNotIn('unit-test-key',json.dumps(result))

    def test_band_permission_denial_is_classified_without_os_error_text(self):
        result=band_bridge._network_exception(PermissionError('sensitive operating system detail'))
        self.assertEqual(result['exception_class'],'PermissionError')
        self.assertEqual(result['network_error_kind'],'socket_permission_denied')
        self.assertNotIn('sensitive operating system detail',json.dumps(result))

    @patch.dict(os.environ, {'BAND_AGENT_API_KEY':'','BAND_CHAT_ID':'room',
                             'BAND_AGENT_KEYS':'{"analyst":"unit-test-key"}',
                             'BAND_AGENT_PEERS':'{}'}, clear=False)
    @patch('app.services.band_bridge.requests.get', side_effect=requests.exceptions.ConnectionError('blocked'))
    def test_band_network_failure_is_not_reported_as_authentication_rejection(self, get):
        report=band_bridge.validate_all_identities()
        analyst=report['agents'][0]
        self.assertEqual(analyst['authentication_status'],'not_verified')
        self.assertEqual(analyst['error_classification'],'network_failure')
        self.assertEqual(analyst['http_status'],None)

    @patch('app.services.band_bridge.requests.utils.get_environ_proxies', return_value={'https':'https://user:password@proxy.example'})
    @patch('app.services.band_bridge.requests.get')
    @patch('app.services.band_bridge.ssl.create_default_context')
    @patch('app.services.band_bridge.socket.socket')
    @patch('app.services.band_bridge.socket.getaddrinfo', return_value=[(2,1,6,'',('203.0.113.4',443))])
    def test_band_connectivity_probe_is_unauthenticated_and_reports_layers(self, dns, sock, ssl_context, get, proxies):
        sock_instance=Mock(); sock.return_value=sock_instance
        wrapped=MagicMock(); ssl_context.return_value.wrap_socket.return_value=wrapped
        response=Mock(); response.status_code=401; get.return_value=response
        result=band_bridge.connectivity_diagnostic()
        self.assertFalse(result['credentials_sent'])
        self.assertFalse(result['messages_sent'])
        self.assertEqual(result['dns']['status'],'resolved')
        self.assertEqual(result['direct_tcp']['status'],'succeeded')
        self.assertEqual(result['direct_tls']['status'],'succeeded')
        self.assertEqual(result['http_probe']['http_status'],401)
        self.assertEqual(result['proxy']['selected_proxy_types'],['https'])
        self.assertEqual(get.call_args.kwargs,{'timeout':(5,8)})
        self.assertNotIn('user:password',json.dumps(result))
        proxies.assert_called_once()

    @patch('app.services.band_bridge.requests.utils.get_environ_proxies', return_value={})
    @patch('app.services.band_bridge.requests.get')
    @patch('app.services.band_bridge.ssl.create_default_context')
    @patch('app.services.band_bridge.socket.socket')
    @patch('app.services.band_bridge.socket.getaddrinfo', return_value=[(2,1,6,'',('203.0.113.4',443))])
    def test_band_connectivity_does_not_claim_tls_when_tcp_is_denied(self, dns, sock, ssl_context, get, proxies):
        sock_instance=Mock(); sock_instance.connect.side_effect=PermissionError('blocked')
        sock.return_value=sock_instance
        response=Mock(); response.status_code=401; get.return_value=response
        result=band_bridge.connectivity_diagnostic()
        self.assertEqual(result['direct_tcp']['network_error_kind'],'socket_permission_denied')
        self.assertEqual(result['direct_tls']['status'],'not_attempted_tcp_unavailable')
        ssl_context.assert_not_called()

    @patch.dict(os.environ, {'BAND_AGENT_API_KEY':'unit-test-band-key','BAND_CHAT_ID':'test-room',
                             'BAND_AGENT_KEYS':'{}','BAND_AGENT_PEERS':'{}'}, clear=False)
    def test_band_single_agent_status_needs_no_role_keys_or_peers(self):
        result=band_bridge.status()
        self.assertTrue(result['configured'])
        self.assertEqual(result['agent_count'],1)
        self.assertEqual(result['sender_identity'],'MARKETMIND')
        self.assertEqual(result['identity_mode'],'single BAND agent')
        self.assertEqual(result['missing_peer_mappings'],[])

    @patch.dict(os.environ, {'BAND_AGENT_API_KEY':'unit-test-band-key','BAND_CHAT_ID':'test-room',
                             'BAND_AGENT_KEYS':'{}','BAND_AGENT_PEERS':'{}'}, clear=False)
    @patch('app.services.band_bridge.requests.post')
    def test_band_single_agent_sends_unmentioned_room_handoff(self, post):
        response=Mock(); response.status_code=201; response.content=b'{"data":{"id":"msg-1"}}'
        response.json.return_value={'data':{'id':'msg-1'}}
        post.return_value=response
        result=band_bridge.send_handoff('analyst','bull','A short handoff.')
        self.assertTrue(result['sent'])
        self.assertEqual(result['submission_status'],'accepted_by_band')
        self.assertEqual(result['message_id'],'msg-1')
        self.assertNotIn('mentions',post.call_args.kwargs['json']['message'])
        self.assertEqual(post.call_args.kwargs['headers']['X-API-Key'],'unit-test-band-key')

    @patch.dict(os.environ, {'BAND_AGENT_API_KEY':'','BAND_CHAT_ID':'test-room',
                             'BAND_AGENT_KEYS':'{}','BAND_AGENT_PEERS':'{}'}, clear=False)
    @patch('app.services.band_bridge.requests.post')
    def test_band_single_agent_missing_key_does_not_send(self, post):
        result=band_bridge.send_test_message()
        self.assertFalse(result['sent'])
        self.assertEqual(result['state'],'credentials_missing')
        self.assertIn('BAND_AGENT_API_KEY',result['missing'])
        post.assert_not_called()

    @patch.dict(os.environ, {'BAND_AGENT_API_KEY':'unit-test-band-key','BAND_CHAT_ID':'test-room',
                             'BAND_AGENT_KEYS':'{}','BAND_AGENT_PEERS':'{}'}, clear=False)
    @patch('app.services.band_bridge.requests.get')
    def test_band_single_agent_identity_and_chat_access_validation(self, get):
        identity=Mock(); identity.status_code=200
        identity.json.return_value={'data':{'id':'marketmind-agent','name':'MARKETMIND','handle':'marketmind'}}
        participants=Mock(); participants.status_code=200
        participants.json.return_value={'data':[{'id':'member-1'}]}
        get.side_effect=[identity,participants]
        result=band_bridge.validate_identity()
        self.assertTrue(result['identity_authenticated'])
        self.assertTrue(result['room_access'])
        self.assertEqual(result['room_access_state'],'operation_succeeded')
        self.assertTrue(all(call.kwargs['headers']['X-API-Key']=='unit-test-band-key' for call in get.call_args_list))

    @patch.dict(os.environ, {
        'BAND_AGENT_API_KEY':'', 'BAND_CHAT_ID':'band-room-1',
        'BAND_AGENT_KEYS':'{"analyst":"key-a","news":"key-n","bull":"key-b","bear":"key-r","risk":"key-risk","chair":"key-c"}',
        'BAND_AGENT_PEERS':'{"analyst":{"id":"id-a","name":"Analyst","handle":"analyst"},"news":{"id":"id-n","name":"News","handle":"news"},"bull":{"id":"id-b","name":"Bull","handle":"bull"},"bear":{"id":"id-r","name":"Bear","handle":"bear"},"risk":{"id":"id-risk","name":"Risk","handle":"risk"},"chair":{"id":"id-c","name":"Chair","handle":"chair"}}'
    }, clear=False)
    @patch('app.services.band_bridge.requests.post')
    @patch('app.services.band_bridge.requests.get')
    def test_band_validate_all_checks_identity_match_and_room_for_each_role(self, get, post):
        replies=[]
        for role, band_id in [('analyst','id-a'),('news','id-n'),('bull','id-b'),('bear','id-r'),('risk','id-risk'),('chair','id-c')]:
            identity=Mock(); identity.status_code=200
            identity.json.return_value={'data':{'id':band_id,'name':role,'handle':role}}
            room=Mock(); room.status_code=200
            room.json.return_value={'data':[]}
            replies.extend([identity,room])
        get.side_effect=replies
        report=band_bridge.validate_all_identities()
        self.assertFalse(report['messages_sent'])
        self.assertEqual(report['summary'],{'total':6,'authenticated':6,'room_access':6,'identity_matches':6})
        self.assertEqual([agent['role'] for agent in report['agents']],band_bridge.ROLES)
        self.assertTrue(all(agent['authentication_status']=='succeeded' for agent in report['agents']))
        self.assertTrue(all(agent['identity_match_status']=='matched' for agent in report['agents']))
        self.assertTrue(all(agent['room_access_status']=='operation_succeeded' for agent in report['agents']))
        self.assertEqual(len(get.call_args_list),12)
        post.assert_not_called()

    @patch.dict(os.environ, {
        'BAND_AGENT_API_KEY':'', 'BAND_CHAT_ID':'band-room-1',
        'BAND_AGENT_KEYS':'{"analyst":"key-a","news":"key-n","bull":"key-b","bear":"key-r","risk":"key-risk","chair":"key-c"}',
        'BAND_AGENT_PEERS':'{"analyst":{"id":"wrong-id","name":"Analyst","handle":"analyst"},"news":{"id":"id-n","name":"News","handle":"news"},"bull":{"id":"id-b","name":"Bull","handle":"bull"},"bear":{"id":"id-r","name":"Bear","handle":"bear"},"risk":{"id":"id-risk","name":"Risk","handle":"risk"},"chair":{"id":"id-c","name":"Chair","handle":"chair"}}'
    }, clear=False)
    @patch('app.services.band_bridge.requests.get')
    def test_band_validate_all_reports_identity_mismatch_without_rejecting_auth(self, get):
        replies=[]
        for role, band_id in [('analyst','id-a'),('news','id-n'),('bull','id-b'),('bear','id-r'),('risk','id-risk'),('chair','id-c')]:
            identity=Mock(); identity.status_code=200
            identity.json.return_value={'data':{'id':band_id}}
            room=Mock(); room.status_code=200; room.json.return_value={'data':[]}
            replies.extend([identity,room])
        get.side_effect=replies
        report=band_bridge.validate_all_identities()
        analyst=report['agents'][0]
        self.assertEqual(analyst['authentication_status'],'succeeded')
        self.assertEqual(analyst['identity_match_status'],'mismatch')
        self.assertEqual(analyst['error_classification'],'identity_mismatch')
        self.assertEqual(analyst['room_access_status'],'operation_succeeded')

    @patch('app.services.market_data._yahoo_quote')
    def test_live_quote_provider_result_is_not_demo(self, yahoo):
        yahoo.return_value={'symbol':'AAPL','price':200.0,'change':2.0,'change_pct':1.0,'source':'Yahoo Finance chart','is_demo':False}
        result=market_data.get_quote('AAPL')
        self.assertFalse(result['is_demo'])
        self.assertEqual(result['source'],'Yahoo Finance chart')

    @patch('app.services.market_data._alpha_quote')
    @patch('app.services.market_data._yahoo_quote', side_effect=RuntimeError('blocked'))
    def test_alpha_vantage_fallback(self, yahoo, alpha):
        alpha.return_value={'symbol':'MSFT','price':400.0,'change':1.0,'change_pct':0.25,'source':'Alpha Vantage','is_demo':False}
        result=market_data.get_quote('MSFT')
        self.assertEqual(result['source'],'Alpha Vantage')
        self.assertFalse(result['is_demo'])

    @patch('app.services.news.requests.get')
    def test_gdelt_articles_are_returned_as_live_with_source_links(self, get):
        response=Mock(); response.raise_for_status.return_value=None
        response.headers={'content-type':'application/json'}
        response.json.return_value={'articles':[{'title':'Company reports earnings','url':'https://example.com/story','domain':'example.com','seendate':'20261121T100000Z'}]}
        get.return_value=response
        news._cache.clear()
        result=news.search_news('Example Corp','EXM')
        self.assertTrue(result['is_live'])
        self.assertEqual(result['articles'][0]['url'],'https://example.com/story')
        self.assertEqual(result['status'],'LIVE_NEWS_AVAILABLE')

    @patch('app.services.news.requests.get')
    def test_gdelt_no_articles_has_explicit_status(self, get):
        response=Mock(); response.raise_for_status.return_value=None
        response.headers={'content-type':'application/json'}
        response.json.return_value={'articles':[]}
        get.return_value=response
        news._cache.clear()
        result=news.search_news('Unknown Corp','UNK')
        self.assertFalse(result['is_live'])
        self.assertEqual(result['status'],'NO_ARTICLES_FOUND')

    @patch('app.services.news.requests.get', side_effect=RuntimeError('network unavailable'))
    def test_gdelt_provider_failure_is_not_live_news(self, get):
        news._cache.clear()
        result=news.search_news('Example Corp','EXM')
        self.assertFalse(result['is_live'])
        self.assertEqual(result['status'],'PROVIDER_UNAVAILABLE')


    @patch.dict(os.environ, {'GEMINI_API_KEY':'test-key','GEMINI_MODEL':'gemini-2.5-flash'}, clear=False)
    @patch('app.services.llm.requests.post')
    def test_gemini_interactions_api_output_is_marked_live(self, post):
        response=Mock(); response.status_code=200; response.raise_for_status.return_value=None
        response.json.return_value={'steps':[{'type':'model_output','content':[{'type':'text','text':'Evidence-based analysis.'}]}]}
        post.return_value=response
        result=llm.generate_result('system','prompt')
        self.assertEqual(result['provider'],'Gemini Interactions API')
        self.assertTrue(result['live'])
        self.assertEqual(result['text'],'Evidence-based analysis.')
        self.assertIn('/v1beta/interactions',post.call_args.args[0])


    @patch.dict(os.environ, {'LYZR_API_KEY':'test-lyzr-key','LYZR_AGENT_IDS':'{"analyst":"agent-123"}'}, clear=False)
    @patch('app.services.llm.requests.post')
    def test_lyzr_role_agent_is_used_when_configured(self, post):
        response=Mock(); response.status_code=200; response.text=''; response.json.return_value={'response':'Lyzr analyst result'}
        post.return_value=response
        result=llm.generate_result('system','prompt',use_lyzr=True,agent_role='analyst')
        self.assertTrue(result['live'])
        self.assertEqual(result['provider'],'Lyzr Inference v3')
        self.assertIn('/v3/inference/chat/',post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs['json']['agent_id'],'agent-123')

    @patch('app.services.news.requests.get')
    def test_yahoo_news_fallback_used_when_gdelt_fails(self, get):
        from requests import HTTPError
        gdelt=Mock(); gdelt.raise_for_status.side_effect=HTTPError('502')
        yahoo=Mock(); yahoo.raise_for_status.return_value=None
        yahoo.json.return_value={'news':[{'content':{'title':'Earnings update','canonicalUrl':{'url':'https://example.com/news'},'provider':{'displayName':'Example'},'pubDate':'2026-11-23T10:00:00Z'}}]}
        get.side_effect=[gdelt,yahoo]
        news._cache.clear()
        result=news.search_news('Example Corp','EXM',force_refresh=True)
        self.assertTrue(result['is_live'])
        self.assertEqual(result['source'],'Yahoo Finance Search News')
        self.assertEqual(result['articles'][0]['url'],'https://example.com/news')

    def test_google_news_rss_valid_xml_parsing(self):
        rss='''<?xml version="1.0"?>
        <rss><channel><item>
          <title>Microsoft reports quarterly earnings</title>
          <link>https://news.example.com/story</link>
          <pubDate>Sun, 23 Nov 2026 10:00:00 GMT</pubDate>
          <source url="https://example.com/">Example News</source>
        </item></channel></rss>'''
        with patch('app.services.news.requests.get') as get:
            response=Mock(); response.raise_for_status.return_value=None; response.text=rss
            get.return_value=response
            articles=news._google_news_rss('Microsoft','MSFT',8)
        self.assertEqual(len(articles),1)
        self.assertEqual(articles[0]['title'],'Microsoft reports quarterly earnings')
        self.assertEqual(articles[0]['url'],'https://news.example.com/story')
        self.assertEqual(articles[0]['published_at'],'Sun, 23 Nov 2026 10:00:00 GMT')
        self.assertEqual(articles[0]['source'],'Example News')
        self.assertIn('q=Microsoft+MSFT',get.call_args.args[0])

    def test_google_news_rss_empty_feed(self):
        rss='<rss><channel></channel></rss>'
        with patch('app.services.news.requests.get') as get:
            response=Mock(); response.raise_for_status.return_value=None; response.text=rss
            get.return_value=response
            articles=news._google_news_rss('Microsoft','MSFT',8)
        self.assertEqual(articles,[])

    def test_google_news_rss_malformed_xml(self):
        with patch('app.services.news.requests.get') as get:
            response=Mock(); response.raise_for_status.return_value=None; response.text='<rss><channel>'
            get.return_value=response
            with self.assertRaises(ValueError):
                news._google_news_rss('Microsoft','MSFT',8)

    def test_google_news_rss_skips_missing_title_or_link(self):
        rss='''<rss><channel>
        <item><title>Missing link</title><pubDate>Sun, 23 Nov 2026 10:00:00 GMT</pubDate></item>
        <item><link>https://news.example.com/no-title</link><pubDate>Sun, 23 Nov 2026 10:00:00 GMT</pubDate></item>
        <item><title>Valid item</title><link>https://news.example.com/valid</link></item>
        </channel></rss>'''
        with patch('app.services.news.requests.get') as get:
            response=Mock(); response.raise_for_status.return_value=None; response.text=rss
            get.return_value=response
            articles=news._google_news_rss('Microsoft','MSFT',8)
        self.assertEqual(len(articles),1)
        self.assertEqual(articles[0]['title'],'Valid item')

    @patch('app.services.news._google_news_rss')
    @patch('app.services.news._yahoo_news')
    @patch('app.services.news._gdelt')
    def test_all_three_providers_failing(self, gdelt, yahoo, google):
        gdelt.side_effect=RuntimeError('GDELT 429')
        yahoo.side_effect=RuntimeError('Yahoo unavailable')
        google.side_effect=RuntimeError('RSS unavailable')
        news._cache.clear()
        result=news.search_news('Example Corp','EXM',force_refresh=True)
        self.assertFalse(result['is_live'])
        self.assertEqual(result['status'],'PROVIDER_UNAVAILABLE')
        self.assertEqual(result['provider_chain'],['GDELT DOC 2.0','Yahoo Finance Search News','Google News RSS'])
        self.assertEqual(len(result['provider_errors']),3)

    @patch('app.services.news._google_news_rss')
    @patch('app.services.news._yahoo_news')
    @patch('app.services.news._gdelt')
    def test_google_news_rss_fallback_articles(self, gdelt, yahoo, google):
        gdelt.side_effect=RuntimeError('GDELT 429')
        yahoo.return_value=[]
        google.return_value=[{'title':'Google fallback headline','url':'https://news.example.com/fallback',
                              'source':'Example Publisher','published_at':'Sun, 23 Nov 2026 10:00:00 GMT',
                              'language':'en','source_country':'US'}]
        news._cache.clear()
        result=news.search_news('Example Corp','EXM',force_refresh=True)
        self.assertTrue(result['is_live'])
        self.assertEqual(result['status'],'LIVE_NEWS_AVAILABLE')
        self.assertEqual(result['source'],'Google News RSS')
        self.assertEqual(result['articles'][0]['url'],'https://news.example.com/fallback')


    @patch.dict(os.environ, {'LYZR_API_KEY':'test-lyzr-key','LYZR_AGENT_IDS':'{"analyst":"agent-123"}','GEMINI_API_KEY':'test-gemini-key'}, clear=False)
    @patch('app.services.llm.requests.post')
    def test_lyzr_failure_falls_back_to_gemini_and_records_attempt(self, post):
        lyzr=Mock(); lyzr.status_code=401; lyzr.text='unauthorized'
        gemini=Mock(); gemini.status_code=200; gemini.json.return_value={'output_text':'Gemini fallback response'}
        post.side_effect=[lyzr,gemini]
        result=llm.generate_result('system','prompt',use_lyzr=True,agent_role='analyst')
        self.assertTrue(result['live'])
        self.assertEqual(result['provider'],'Gemini Interactions API')
        self.assertEqual(result['attempts'][0]['provider'],'Lyzr')
        self.assertEqual(result['attempts'][0]['status'],'failed')

if __name__=='__main__': unittest.main()
