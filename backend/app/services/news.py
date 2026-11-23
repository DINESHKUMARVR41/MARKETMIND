"""Live public-news search via GDELT DOC 2.0. No API key required; cache limits repeat calls."""
import time, requests
from urllib.parse import quote

_cache={}

def search_news(company, symbol, limit=8):
    key=f'{company}|{symbol}'.lower(); now=time.time()
    cached=_cache.get(key)
    if cached and now-cached['at']<300: return {**cached['data'],'cached':True}
    query=f'("{company}" OR "{symbol}")'
    params={'query':query,'mode':'ArtList','format':'json','maxrecords':min(max(limit,1),25),'timespan':'7d','sort':'DateDesc'}
    try:
        r=requests.get('https://api.gdeltproject.org/api/v2/doc/doc',params=params,headers={'User-Agent':'MARKETMIND/1.0 educational research'},timeout=18)
        r.raise_for_status()
        if 'json' not in r.headers.get('content-type','').lower(): raise ValueError('GDELT returned a non-JSON response')
        raw=r.json()
    except requests.Timeout:
        data={'query':query,'source':'GDELT DOC 2.0','status':'PROVIDER_UNAVAILABLE','is_live':False,'articles':[],'count':0,'window':'7 days','retrieved_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'error':'GDELT request timed out','warning':'Live news provider unavailable; do not infer that no relevant news exists.'}
        _cache[key]={'at':now,'data':data}; return data
    except Exception as exc:
        data={'query':query,'source':'GDELT DOC 2.0','status':'PROVIDER_UNAVAILABLE','is_live':False,'articles':[],'count':0,'window':'7 days','retrieved_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'error':str(exc)[:220],'warning':'Live news provider unavailable; do not infer that no relevant news exists.'}
        _cache[key]={'at':now,'data':data}; return data
    articles=[]
    for a in raw.get('articles',[]):
        articles.append({'title':a.get('title'),'url':a.get('url'),'source':a.get('domain') or a.get('sourceCountry'),'published_at':a.get('seendate'),'language':a.get('language'),'source_country':a.get('sourceCountry')})
    status='LIVE_NEWS_AVAILABLE' if articles else 'NO_ARTICLES_FOUND'
    data={'query':query,'source':'GDELT DOC 2.0','status':status,'is_live':bool(articles),'articles':articles,'count':len(articles),'window':'7 days','retrieved_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
      'warning':'GDELT coverage is broad but not exhaustive; headlines are leads, not verified facts.' if articles else 'GDELT completed successfully but returned no matching articles.'}
    _cache[key]={'at':now,'data':data}; return data
