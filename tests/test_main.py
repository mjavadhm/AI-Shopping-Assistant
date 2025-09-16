from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_sanity_check_ping():
    """Tests the ping/pong sanity check."""
    payload = {
        "chat_id": "sanity-check-ping",
        "messages": [{"type": "user", "content": "ping"}]
    }
    response = client.post("/chat", json=payload)
    
    assert response.status_code == 200
    
    data = response.json()
    assert data["message"] == "pong"
    assert data["base_random_keys"] is None
    assert data["member_random_keys"] is None

def test_sanity_check_base_key():
    """Tests the return of a base_random_key."""
    test_key = "my-test-base-key"
    payload = {
        "chat_id": "sanity-check-base-key",
        "messages": [{"type": "user", "content": f"return base random key: {test_key}"}]
    }
    response = client.post("/chat", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["base_random_keys"] == [test_key]
    assert data["message"] is None

def test_sanity_check_member_key():
    """Tests the return of a member_random_key."""
    test_key = "my-test-member-key"
    payload = {
        "chat_id": "sanity-check-member-key",
        "messages": [{"type": "user", "content": f"return member random key: {test_key}"}]
    }
    response = client.post("/chat", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["member_random_keys"] == [test_key]
    assert data["message"] is None