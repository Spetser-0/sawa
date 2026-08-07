"""
اختبارات /payments/webhook — SECURITY 1
التوقيع يُحسب على البايتات الخام (بعد حذف حقل sign فقط)، وليس على إعادة
تسلسل القاموس المُحلَّل. لا تحقق = رفض كامل (503)، وليس تجاوزاً للتحقق.
"""
import json
import base64
import hashlib
import pytest
from tests.conftest import client


TEST_API_KEY = "test-cryptomus-webhook-key"


def _sign(payload: dict, api_key: str) -> str:
    # httpx (المستخدم في TestClient) يُسلسل JSON بفواصل مضغوطة بدون مسافات
    # (نفس separators=(",", ":"))، خلافاً لـ json.dumps الافتراضي في بايثون
    # الذي يضيف مسافة بعد كل فاصلة/نقطتين. لازم نطابق تسلسل الطلب الفعلي
    # المُرسَل عبر الشبكة حتى يتطابق التوقيع هنا مع ما يحسبه الخادم.
    body_str = base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()
    return hashlib.md5(f"{body_str}{api_key}".encode()).hexdigest()


class TestPaymentWebhookSecurity:
    def test_503_when_api_key_not_configured(self, client, monkeypatch):
        """أهم اختبار أمني: غياب المفتاح يعني رفض الطلب بالكامل (503)،
        وليس تجاوز التحقق من التوقيع بصمت."""
        monkeypatch.setattr("app.routers.payments.CRYPTOMUS_API_KEY", "")

        res = client.post("/api/payments/webhook", json={"status": "paid"})
        assert res.status_code == 503

    def test_401_on_bad_signature(self, client, monkeypatch):
        monkeypatch.setattr("app.routers.payments.CRYPTOMUS_API_KEY", TEST_API_KEY)

        payload = {
            "status": "paid",
            "amount": "7.00",
            "order_id": "order_123",
            "additional_data": json.dumps({"user_id": "some-user", "plan": "pro"}),
            "sign": "0" * 32,  # توقيع خاطئ عمداً
        }
        res = client.post("/api/payments/webhook", json=payload)
        assert res.status_code == 401

    def test_401_when_sign_field_missing(self, client, monkeypatch):
        monkeypatch.setattr("app.routers.payments.CRYPTOMUS_API_KEY", TEST_API_KEY)

        res = client.post("/api/payments/webhook", json={"status": "paid", "amount": "7.00"})
        assert res.status_code == 401

    def test_valid_signature_accepted_for_unknown_user(self, client, monkeypatch, db_session):
        """توقيع صحيح فعلياً (نفس خوارزمية Cryptomus: md5(base64(json)+key))
        يجب أن يمر التحقق — لكن user_id غير موجود فيرجع 404 (وليس 401)،
        ما يؤكد أن الرفض في الاختبارات الأخرى كان بسبب التوقيع تحديداً."""
        monkeypatch.setattr("app.routers.payments.CRYPTOMUS_API_KEY", TEST_API_KEY)

        payload = {
            "status": "paid",
            "amount": "7.00",
            "order_id": "order_456",
            "additional_data": json.dumps({"user_id": "no-such-user", "plan": "pro"}),
        }
        payload["sign"] = _sign(payload, TEST_API_KEY)

        res = client.post("/api/payments/webhook", json=payload)
        assert res.status_code == 404  # تجاوز التوقيع بنجاح، فشل لاحقاً في إيجاد المستخدم

    def test_valid_signature_activates_subscription(self, client, monkeypatch, db_session):
        monkeypatch.setattr("app.routers.payments.CRYPTOMUS_API_KEY", TEST_API_KEY)

        reg = client.post("/api/auth/register", json={
            "name": "مشترك",
            "email": "subscriber@test.com",
            "password": "Pass1234!",
        })
        user_id = reg.json()["user"]["id"]

        payload = {
            "status": "paid",
            "amount": "7.00",
            "order_id": "order_789",
            "additional_data": json.dumps({"user_id": user_id, "plan": "pro"}),
        }
        payload["sign"] = _sign(payload, TEST_API_KEY)

        res = client.post("/api/payments/webhook", json=payload)
        assert res.status_code == 200

        from app.database import User
        user = db_session.query(User).filter(User.id == user_id).first()
        assert user.plan == "pro"

    def test_signature_tolerant_to_key_reordering(self, client, monkeypatch):
        """التحقق يعتمد على البايتات الخام كما استُقبلت — طالما حُسب التوقيع
        على نفس البايتات (بأي ترتيب مفاتيح أرسله Cryptomus)، يجب أن يمر."""
        monkeypatch.setattr("app.routers.payments.CRYPTOMUS_API_KEY", TEST_API_KEY)

        payload = {
            "order_id": "order_999",
            "status": "paid",
            "additional_data": json.dumps({"user_id": "reorder-user", "plan": "teams"}),
            "amount": "12.00",
        }
        payload["sign"] = _sign(payload, TEST_API_KEY)

        res = client.post("/api/payments/webhook", json=payload)
        # 404 (مستخدم غير موجود) يعني نجح التحقق من التوقيع فعلياً
        assert res.status_code == 404
