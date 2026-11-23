"""Local smoke test: run from backend after installing requirements."""
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    assert client.get('/api/health').status_code == 200
    assert len(client.get('/api/agents').json()) == 6
    result = client.post('/api/analyze', json={
        'symbol': 'MSFT', 'company': 'Microsoft', 'investment_amount': 1000,
        'horizon': 'month', 'risk_tolerance': 'balanced', 'max_position_pct': 20, 'portfolio_value': 5000
    })
    assert result.status_code == 200, result.text
    payload = result.json()
    assert len(payload['events']) == 6
    assert len(payload['handoffs']) == 6
    assert payload['execution'] == 'PAPER_ONLY'
    assert len(payload['model_calls']) == 6
    assert payload['integration_summary']['total_agents'] == 6
    assert 'is_demo' in payload['quote']
    assert payload['requested_investment_amount'] == 1000
    assert payload['investment_amount'] <= payload['portfolio_value'] * payload['suggested_allocation_pct'] / 100
    assert 'is_live' in payload['news']
    assert all('provider' in event and 'live_reasoning' in event for event in payload['events'])
    print('MARKETMIND smoke test passed:', payload['decision'], 'run', payload['run_id'])
