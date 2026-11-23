"""Optional Band message bridge. Uses real mention-routed Agent API messages.
Each sender requires its own Agent API key; target participants must already
be members of BAND_CHAT_ID. Events are not used as a substitute for messages.
"""
import os, json, requests
BASE='https://app.band.ai/api/v1/agent'

def _config():
    try: keys=json.loads(os.getenv('BAND_AGENT_KEYS','{}'))
    except Exception: keys={}
    try: peers=json.loads(os.getenv('BAND_AGENT_PEERS','{}'))
    except Exception: peers={}
    return keys,peers,os.getenv('BAND_CHAT_ID','').strip()

def status():
    keys,peers,room=_config()
    roles=['analyst','news','bull','bear','risk','chair']
    missing_keys=[role for role in roles if not keys.get(role)]
    missing_peers=[role for role in roles if not peers.get(role,{}).get('id') or not peers.get(role,{}).get('handle')]
    ready=bool(room and not missing_keys and not missing_peers)
    return {'configured':ready,'chat_id_present':bool(room),'agents_with_keys':len(keys),'peer_handles':len(peers),'missing_agent_keys':missing_keys,'missing_peer_mappings':missing_peers,'mode':'live mention-routed messages' if ready else 'local collaboration; BAND setup incomplete'}

def send_handoff(sender, recipient, content):
    keys,peers,room=_config()
    if not (room and keys.get(sender) and peers.get(recipient)):
        return {'sent':False,'mode':'local','reason':'Missing BAND_CHAT_ID, sender agent key, or recipient participant mapping.'}
    peer=peers[recipient]
    handle=peer.get('handle','').lstrip('@')
    payload={'message':{'content':f'@{handle} MARKETMIND handoff: {content}','mentions':[{'id':peer['id'],'name':peer['name'],'handle':handle}]}}
    try:
        r=requests.post(f'{BASE}/chats/{room}/messages',headers={'X-API-Key':keys[sender],'Content-Type':'application/json'},json=payload,timeout=10)
        r.raise_for_status()
        return {'sent':True,'mode':'BAND','recipient':recipient,'response':r.json() if r.content else {}}
    except Exception as e:
        return {'sent':False,'mode':'BAND','reason':str(e)}
