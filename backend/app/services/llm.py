"""LLM provider adapter with truthful Gemini and fallback metadata."""
import os, json, requests

def generate_result(system, prompt, use_lyzr=False, agent_role=None):
    key=os.getenv('GEMINI_API_KEY','').strip()
    if not key:
        return {'text':None,'provider':'deterministic fallback','live':False,'status_code':None,'error_code':'GEMINI_KEY_MISSING','error':'GEMINI_API_KEY is not configured'}
    model=os.getenv('GEMINI_MODEL','gemini-2.5-flash').strip()
    try:
        r=requests.post(
            'https://generativelanguage.googleapis.com/v1beta/interactions',
            headers={'x-goog-api-key':key,'Content-Type':'application/json'},
            json={'model':model,'input':prompt,'system_instruction':system,'store':False},
            timeout=35)
        status=r.status_code if isinstance(r.status_code,int) else 200
        if status >= 400:
            try: detail=r.json()
            except Exception: detail={'message':r.text[:220]}
            message=detail.get('error',{}).get('message') if isinstance(detail,dict) else None
            message=message or detail.get('message') if isinstance(detail,dict) else None
            error_code='GEMINI_RATE_LIMITED' if status==429 else 'GEMINI_AUTH_ERROR' if status in (401,403) else 'GEMINI_HTTP_ERROR'
            return {'text':None,'provider':'deterministic fallback','live':False,'status_code':status,'error_code':error_code,'error':str(message or f'Gemini returned HTTP {status}')[:220]}
        data=r.json()
        answer=data.get('output_text')
        if not answer:
            for step in data.get('steps',[]):
                if step.get('type')=='model_output':
                    answer='\n'.join(part.get('text','') for part in step.get('content',[]) if part.get('type')=='text').strip()
                    if answer: break
        if answer:
            return {'text':answer,'provider':'Gemini Interactions API','live':True,'status_code':status,'error_code':None,'error':None}
        return {'text':None,'provider':'deterministic fallback','live':False,'status_code':status,'error_code':'GEMINI_EMPTY_RESPONSE','error':'Gemini returned no text output'}
    except requests.Timeout:
        return {'text':None,'provider':'deterministic fallback','live':False,'status_code':None,'error_code':'GEMINI_TIMEOUT','error':'Gemini request timed out'}
    except requests.RequestException as exc:
        return {'text':None,'provider':'deterministic fallback','live':False,'status_code':getattr(getattr(exc,'response',None),'status_code',None),'error_code':'GEMINI_REQUEST_ERROR','error':str(exc)[:220]}
    except Exception as exc:
        return {'text':None,'provider':'deterministic fallback','live':False,'status_code':None,'error_code':'GEMINI_RESPONSE_ERROR','error':str(exc)[:220]}

def _lyzr_roles():
    try: return json.loads(os.getenv('LYZR_AGENT_IDS','{}'))
    except Exception: return {}

def provider_status():
    roles=_lyzr_roles(); has_ids=bool(os.getenv('LYZR_AGENT_ID') or roles)
    return {'gemini':{'configured':bool(os.getenv('GEMINI_API_KEY')),'model':os.getenv('GEMINI_MODEL','gemini-2.5-flash')},
      'lyzr':{'configured':bool(os.getenv('LYZR_API_KEY') and has_ids),'agent_id_present':has_ids,'role_agents_configured':len(roles)}}
