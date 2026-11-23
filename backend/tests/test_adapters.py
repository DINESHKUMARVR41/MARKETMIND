import os
import unittest
from unittest.mock import patch, Mock
from app.services import market_data, news, llm

class AdapterTests(unittest.TestCase):
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
        response=Mock(); response.raise_for_status.return_value=None
        response.json.return_value={'steps':[{'type':'model_output','content':[{'type':'text','text':'Evidence-based analysis.'}]}]}
        post.return_value=response
        result=llm.generate_result('system','prompt')
        self.assertEqual(result['provider'],'Gemini Interactions API')
        self.assertTrue(result['live'])
        self.assertEqual(result['text'],'Evidence-based analysis.')
        self.assertIn('/v1beta/interactions',post.call_args.args[0])

if __name__=='__main__': unittest.main()
