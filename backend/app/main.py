import os
import re
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from app.models import AnalyzeRequest
from app.database import init_db, save_run, save_trade, list_runs, get_run, list_trades, trade_exists_for_run, save_adal_event, list_adal_events
from app.services.market_data import get_quote, get_history
from app.services.news import search_news
from app.services.llm import provider_status
from app.services.band_bridge import status as band_status, validate_identity as band_validate, validate_all_identities as band_validate_all, send_test_message as band_test_message, connectivity_diagnostic as band_connectivity
from app.agents.committee import run_committee, AGENTS
from app.services.finch import status as finch_status, doctor as finch_doctor
from app.services.agent37 import status as agent37_status, provision_instance as agent37_provision, run_agent as agent37_run

app=FastAPI(title='MARKETMIND API',version='1.1.0',description='Six-agent investment committee with debate, risk gate and paper trading.')
app.add_middleware(CORSMiddleware,allow_origins=[os.getenv('FRONTEND_ORIGIN','http://localhost:5173'),'http://127.0.0.1:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@app.on_event('startup')
def startup(): init_db()
@app.get('/api/health')
def health():
    return {'status':'ok','app':'MARKETMIND','agents':len(AGENTS),'providers':provider_status(),'market_data':{'yahoo_chart':'attempted_per_request','alpha_vantage_configured':bool(os.getenv('ALPHA_VANTAGE_API_KEY'))},'news':{'providers':['GDELT DOC 2.0','Yahoo Finance Search News','Google News RSS'],'no_key_required':True},'band':band_status(),'adal_webhook_configured':bool(os.getenv('ADAL_WEBHOOK_URL')),'agent37':agent37_status(),'agent37_deployment_configured':agent37_status().get('inference_configured', False),'finch':finch_status()}
@app.get('/api/integrations')
def integrations():
    return {'providers': provider_status(), 'band': band_status(), 'finch': finch_status(),
            'adal': {'ingest_url_configured': bool(os.getenv('ADAL_WEBHOOK_URL')), 'shared_token_configured': bool(os.getenv('ADAL_WEBHOOK_TOKEN')),
                     'note': 'The Adal CLI token is not an inbound webhook bearer token. ADAL_WEBHOOK_TOKEN is an optional secret you generate and configure at the destination.'},
            'agent37': agent37_status()}

@app.get('/api/integrations/diagnostics')
def integration_diagnostics():
    """Report local configuration only. This endpoint makes no provider or CLI calls."""
    band = band_status()
    finch = finch_status()
    a37 = agent37_status()
    band_missing = []
    if not band.get('chat_id_present'):
        band_missing.append('BAND_CHAT_ID')
    if band.get('missing_agent_keys'):
        band_missing.append('BAND_AGENT_API_KEY or BAND_AGENT_KEYS')
    if band.get('missing_peer_mappings'):
        band_missing.append('BAND_AGENT_PEERS')
    band_state = 'credentials_missing' if band_missing else 'configured_unverified'
    adal_missing = [] if os.getenv('ADAL_WEBHOOK_URL', '').strip() else ['ADAL_WEBHOOK_URL']
    agent37_missing = [name for name, present in (
        ('AGENT37_API_KEY', a37.get('api_key_configured')),
        ('AGENT37_INSTANCE_URL', a37.get('instance_configured')),
        ('AGENT37_INSTANCE_API_KEY', bool(os.getenv('AGENT37_INSTANCE_API_KEY', '').strip())),
    ) if not present]
    return {
        'network_calls_made': False,
        'outcome_states': ['credentials_missing', 'authentication_rejected', 'network_failure',
                           'authentication_succeeded', 'operation_succeeded', 'configured_unverified'],
        'band': {'state': band_state, 'missing': band_missing, 'identity_authentication': 'not_checked',
                 'message_operation': 'not_checked', 'details': band},
        'finch': {'local_skills_state': 'operation_succeeded' if all(
                      item.get('loaded') for item in finch.get('skills', {}).values()) else 'local_skills_incomplete',
                  'cli_state': 'installed' if finch.get('finch_cli_installed') else 'cli_missing',
                  'remote_mcp_state': 'configured_unverified' if finch.get('remote_mcp_endpoint_configured') else 'credentials_missing',
                  'remote_authentication': 'not_checked', 'remote_operation': 'not_implemented_in_marketmind',
                  'details': finch},
        'adal': {'state': 'credentials_missing' if adal_missing else 'configured_unverified',
                 'missing': adal_missing,
                 'shared_token': 'configured' if os.getenv('ADAL_WEBHOOK_TOKEN', '').strip() else 'optional_but_recommended_missing',
                 'inbound_authentication': 'not_checked', 'outbound_delivery': 'not_checked'},
        'agent37': {'state': 'credentials_missing' if agent37_missing else 'configured_unverified',
                    'missing': agent37_missing, 'authentication': 'not_checked',
                    'hosted_inference_operation': 'not_checked', 'provisioning': 'not_attempted',
                    'details': a37},
    }

@app.post('/api/integrations/band/validate')
def validate_band():
    return band_validate(os.getenv('BAND_VALIDATE_ROLE', 'analyst'))

@app.post('/api/integrations/band/validate-all')
def validate_all_band_agents():
    return band_validate_all()

@app.post('/api/integrations/band/connectivity')
def diagnose_band_connectivity():
    return band_connectivity()

@app.post('/api/integrations/band/test-message')
def send_band_test_message():
    """Send a harmless chat post only when explicitly requested by an operator."""
    result = band_test_message()
    if not result.get('sent'):
        code = 400 if result.get('state') == 'credentials_missing' else 502
        raise HTTPException(code, {'state': result.get('state', 'operation_failed'),
                                   'submission_status': result.get('submission_status'),
                                   'message': result.get('error') or result.get('reason')})
    return result

@app.post('/api/integrations/llm/test')
def test_llm(payload: dict):
    from app.services.llm import generate_result
    role = str(payload.get('role', 'chair')).lower()
    if role not in {'analyst','news','bull','bear','risk','chair'}:
        raise HTTPException(400, 'Unknown committee role.')
    prompt = str(payload.get('prompt', 'Reply exactly: MARKETMIND provider connection verified.'))[:4000]
    result = generate_result('You are a connection-test assistant. Reply briefly.', prompt, use_lyzr=True, agent_role=role)
    if not result.get('live'):
        raise HTTPException(502, {'message': 'No live LLM provider returned a response.', 'attempts': result.get('attempts', [])})
    return {'ok': True, 'role': role, 'provider': result.get('provider'), 'status_code': result.get('status_code'),
            'response': result.get('text'), 'attempts': result.get('attempts', [])}

@app.post('/api/integrations/finch/doctor')
def finch_mcp_doctor():
    return finch_doctor()

@app.post('/api/integrations/agent37/provision')
def provision_agent37(payload: dict = None):
    # Explicit action only: Agent 37 compute/storage may be metered.
    result = agent37_provision((payload or {}).get('template'))
    if not result.get('ok'):
        raise HTTPException(502, {'state': result.get('state', 'operation_failed'),
                                  'operation_succeeded': False,
                                  'message': result.get('error', 'Agent 37 provisioning failed')})
    return result

@app.post('/api/integrations/agent37/test')
def test_agent37(payload: dict):
    prompt = str(payload.get('prompt', 'Reply with: MARKETMIND Agent 37 connection verified.'))[:6000]
    result = agent37_run(prompt, payload.get('previous_response_id'))
    if not result.get('live'):
        raise HTTPException(502, {'state': result.get('state', 'operation_failed'),
                                  'operation_succeeded': False,
                                  'message': result.get('error', 'Agent 37 inference failed')})
    return result

@app.get('/api/adal/events')
def adal_events():
    return list_adal_events()

@app.post('/api/webhooks/adal')
async def receive_adal_webhook(payload: dict, request: Request):
    import hmac
    expected = os.getenv('ADAL_WEBHOOK_TOKEN', '').strip()
    supplied = os.getenv('ADAL_WEBHOOK_HEADER', 'X-MarketMind-Webhook-Token')
    if expected and not hmac.compare_digest(request.headers.get(supplied, ''), expected):
        raise HTTPException(401, 'Invalid webhook authentication token.')
    event_id = str(payload.get('event_id') or payload.get('id') or request.headers.get('X-Event-Id') or '')
    if not event_id:
        event_id = __import__('hashlib').sha256(__import__('json').dumps(payload, sort_keys=True).encode()).hexdigest()
    def redact(value):
        if isinstance(value, dict):
            return {key: ('[REDACTED]' if re.search(r'(secret|token|api[_-]?key|authorization|password|credential)', str(key), re.I)
                          else redact(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value
    created = save_adal_event(event_id, redact(payload))
    return {'accepted': True, 'duplicate': not created, 'event_id': event_id}

@app.get('/api/agents')
def agents(): return AGENTS
@app.get('/api/quote/{symbol}')
def quote(symbol:str):
    try: return get_quote(symbol)
    except ValueError as exc: raise HTTPException(400, str(exc))
@app.get('/api/history-prices/{symbol}')
def price_history(symbol:str, range_:str='1mo', interval:str='1d'):
    try: return get_history(symbol,range_,interval)
    except Exception as exc: raise HTTPException(502,f'Live price history unavailable: {str(exc)[:180]}')
@app.get('/api/news/{symbol}')
def news(symbol:str, company:str=''):
    return search_news(company or symbol,symbol)
@app.post('/api/analyze')
def analyze(req:AnalyzeRequest):
    try: quote=get_quote(req.symbol)
    except ValueError as exc: raise HTTPException(400, str(exc))
    report=run_committee(req,quote)
    run_id=save_run(report); report['run_id']=run_id
    # Persist the same replay shape returned to the caller.
    from app.database import update_run_report
    update_run_report(run_id, report)
    return report
@app.post('/api/paper-trade/{run_id}')
def paper_trade(run_id:int):
    run=get_run(run_id)
    if not run: raise HTTPException(404,'Analysis run not found')
    r=run['report']
    if r['decision']!='BUY' or not r['risk_approved']:
        raise HTTPException(400,'Paper order blocked: decision is not BUY or risk gate did not approve.')
    if trade_exists_for_run(run_id):
        raise HTTPException(409,'A paper trade has already been recorded for this analysis run.')
    q=r['quote']['price']; amount=r['investment_amount']; qty=round(amount/q,6)
    trade_id=save_trade(run_id,r['symbol'],'BUY',qty,q,amount)
    if trade_id is None:
        raise HTTPException(409,'A paper trade has already been recorded for this analysis run.')
    return {'trade_id':trade_id,'run_id':run_id,'symbol':r['symbol'],'side':'BUY','quantity':qty,'price':q,'amount':amount,'status':'PAPER','message':'Simulated order recorded. No real money moved.'}
@app.get('/api/history')
def history(): return list_runs()
@app.get('/api/history/{run_id}')
def history_detail(run_id:int):
    item=get_run(run_id)
    if not item: raise HTTPException(404,'Run not found')
    return item
@app.get('/api/trades')
def trades(): return list_trades()
@app.post('/api/adal/notify/{run_id}')
def adal_notify(run_id:int):
    import requests
    from app.database import get_run
    url=os.getenv('ADAL_WEBHOOK_URL')
    if not url: raise HTTPException(400,'Configure ADAL_WEBHOOK_URL first.')
    item=get_run(run_id)
    if not item: raise HTTPException(404,'Run not found')
    headers={'Content-Type':'application/json','X-Event-Id':f'marketmind-run-{run_id}'}
    if os.getenv('ADAL_WEBHOOK_TOKEN'): headers[os.getenv('ADAL_WEBHOOK_HEADER','X-MarketMind-Webhook-Token')]=os.getenv('ADAL_WEBHOOK_TOKEN')
    try:
        res=requests.post(url,json={'event':'marketmind.analysis.completed','report':item['report']},headers=headers,timeout=12)
        if res.status_code >= 400:
            state = 'authentication_rejected' if res.status_code in (401, 403) else 'operation_failed'
            raise HTTPException(502, {'state': state, 'operation_succeeded': False,
                                      'message': f'AdaL ingest request failed: HTTP {res.status_code}'})
        return {'sent':True,'state':'operation_succeeded','operation_succeeded':True,
                'accepted_by_adal':True,'status_code':res.status_code,
                'note':'AdaL accepted the inbound request. Check AdaL Delivery history to confirm forwarding to its configured Destination.'}
    except HTTPException:
        raise
    except requests.Timeout:
        raise HTTPException(502, {'state':'network_failure','operation_succeeded':False,'message':'AdaL ingest request timed out'})
    except requests.RequestException:
        raise HTTPException(502, {'state':'network_failure','operation_succeeded':False,'message':'AdaL ingest request could not reach the configured service'})
