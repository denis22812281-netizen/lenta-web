"""Тесты PWA Push-уведомлений."""


def test_vapid_key_endpoint_public(client):
    """VAPID-ключ доступен без авторизации и возвращает JSON."""
    r = client.get("/api/push/vapid-public-key")
    assert r.status_code == 200
    data = r.json()
    assert "key" in data
    assert "enabled" in data
    assert isinstance(data["enabled"], bool)


def test_push_subscribe_requires_auth(client):
    """Подписка на push без авторизации — редирект на логин."""
    r = client.post("/api/push/subscribe",
                    json={"endpoint": "https://example.com/push/test",
                          "keys": {"p256dh": "key1", "auth": "authval"}},
                    follow_redirects=False)
    assert r.status_code in (302, 401, 403)


def test_push_subscribe_and_unsubscribe(auth_client):
    """Авторизованный пользователь может подписаться и отписаться."""
    endpoint = "https://fcm.googleapis.com/fake-push-endpoint-for-test"

    r = auth_client.post("/api/push/subscribe", json={
        "endpoint": endpoint,
        "keys": {"p256dh": "fake_p256dh_key", "auth": "fake_auth_key"},
    })
    assert r.status_code == 200
    assert r.json().get("ok") is True

    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    sub = db.query(models.PushSubscription).filter_by(endpoint=endpoint).first()
    db.close()
    assert sub is not None
    assert sub.p256dh == "fake_p256dh_key"

    r = auth_client.request("DELETE", "/api/push/subscribe",
                            json={"endpoint": endpoint})
    assert r.status_code == 200

    db = TestingSessionLocal()
    gone = db.query(models.PushSubscription).filter_by(endpoint=endpoint).first()
    db.close()
    assert gone is None


def test_push_subscribe_idempotent(auth_client):
    """Повторная подписка с тем же endpoint обновляет запись, не дублирует."""
    endpoint = "https://fcm.googleapis.com/fake-idempotent-endpoint"

    auth_client.post("/api/push/subscribe", json={
        "endpoint": endpoint,
        "keys": {"p256dh": "key_v1", "auth": "auth_v1"},
    })
    auth_client.post("/api/push/subscribe", json={
        "endpoint": endpoint,
        "keys": {"p256dh": "key_v2", "auth": "auth_v2"},
    })

    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    subs = db.query(models.PushSubscription).filter_by(endpoint=endpoint).all()
    db.close()
    assert len(subs) == 1
    assert subs[0].p256dh == "key_v2"
    auth_client.request("DELETE", "/api/push/subscribe", json={"endpoint": endpoint})
