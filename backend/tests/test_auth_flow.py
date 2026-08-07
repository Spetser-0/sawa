"""
اختبارات التدفق الكامل للمصادقة — Feature 9.7
5 اختبارات E2E تغطي: تسجيل/دخول/خروج، نسيان كلمة المرور، دوران التوكن، تغيير كلمة المرور، الإعدادات
"""
from datetime import datetime, timedelta
from tests.conftest import client, auth_client, db_session
import pytest


# ══════════════════════════════════════════════════════
#  1. تسجيل → دخول → جلب بيانات → خروج
# ══════════════════════════════════════════════════════
class TestRegisterLoginMeLogout:
    def test_register_returns_cookies(self, client):
        res = client.post("/api/auth/register", json={
            "name": "أحمد",
            "email": "ahmed@test.com",
            "password": "Secret123!",
        })
        assert res.status_code == 201
        body = res.json()
        assert "user" in body
        assert body["user"]["email"] == "ahmed@test.com"
        assert body["user"]["name"] == "أحمد"

        cookies = {k: v for k, v in client.cookies.items()}
        assert "sawa_access_token" in cookies
        assert "sawa_refresh" in cookies

    def test_me_returns_user_after_register(self, client):
        client.post("/api/auth/register", json={
            "name": "سارة",
            "email": "sara@test.com",
            "password": "Strong123!",
        })
        res = client.get("/api/auth/me")
        assert res.status_code == 200
        assert res.json()["email"] == "sara@test.com"

    def test_login_sets_cookies(self, client):
        client.post("/api/auth/register", json={
            "name": "محمد",
            "email": "mo@test.com",
            "password": "MyPass123!",
        })
        client.cookies.clear()

        res = client.post("/api/auth/login", json={
            "email": "mo@test.com",
            "password": "MyPass123!",
        })
        assert res.status_code == 200
        cookies = {k: v for k, v in client.cookies.items()}
        assert "sawa_access_token" in cookies
        assert "sawa_refresh" in cookies

    def test_login_returns_access_token_in_body(self, client):
        """BLOCKER 4: iOS Safari يحجب الكوكيز عبر-النطاقات (ITP) — لازم
        access_token يرجع في جسم الاستجابة كبديل Bearer."""
        client.post("/api/auth/register", json={
            "name": "آيفون",
            "email": "ios@test.com",
            "password": "IosPass123!",
        })
        client.cookies.clear()
        res = client.post("/api/auth/login", json={
            "email": "ios@test.com",
            "password": "IosPass123!",
        })
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body and body["access_token"]
        assert body["token_type"] == "bearer"
        assert "refresh" not in body  # التوكن الحساس يبقى في كوكيز httpOnly فقط

    def test_register_returns_access_token_in_body(self, client):
        res = client.post("/api/auth/register", json={
            "name": "تسجيل",
            "email": "register-token@test.com",
            "password": "RegPass123!",
        })
        assert res.status_code == 201
        body = res.json()
        assert "access_token" in body and body["access_token"]
        assert body["token_type"] == "bearer"

    def test_bearer_header_works_without_cookies(self, client):
        """يتحقق أن get_current_user يقبل Authorization: Bearer عند غياب
        الكوكيز تماماً — وهو بالضبط سيناريو iOS Safari."""
        res = client.post("/api/auth/register", json={
            "name": "بيرر",
            "email": "bearer@test.com",
            "password": "BearerPass123!",
        })
        access_token = res.json()["access_token"]
        client.cookies.clear()

        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert res.status_code == 200
        assert res.json()["email"] == "bearer@test.com"

    def test_logout_clears_cookies(self, client):
        client.post("/api/auth/register", json={
            "name": "خالد",
            "email": "khaled@test.com",
            "password": "Pass1234!",
        })
        res = client.post("/api/auth/logout")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        cookies = {k: v for k, v in client.cookies.items()}
        assert "sawa_access_token" not in cookies or cookies.get("sawa_access_token") == ""
        assert "sawa_refresh" not in cookies or cookies.get("sawa_refresh") == ""

    def test_me_returns_401_after_logout(self, client):
        client.post("/api/auth/register", json={
            "name": "فاطمة",
            "email": "fatima@test.com",
            "password": "Pass1234!",
        })
        client.post("/api/auth/logout")
        res = client.get("/api/auth/me")
        assert res.status_code == 401

    def test_duplicate_email_rejected(self, client):
        client.post("/api/auth/register", json={
            "name": "أول",
            "email": "dup@test.com",
            "password": "Pass1234!",
        })
        res = client.post("/api/auth/register", json={
            "name": "ثاني",
            "email": "dup@test.com",
            "password": "Other123!",
        })
        assert res.status_code == 400
        assert res.json()["error_code"] == "EMAIL_EXISTS"

    def test_wrong_password_returns_error_code(self, client):
        client.post("/api/auth/register", json={
            "name": "试探",
            "email": "wrong@test.com",
            "password": "Correct123!",
        })
        client.cookies.clear()
        res = client.post("/api/auth/login", json={
            "email": "wrong@test.com",
            "password": "Wrong999!",
        })
        assert res.status_code == 401
        assert res.json()["error_code"] == "INVALID_CREDENTIALS"

    def test_unknown_email_returns_same_error_code_as_wrong_password(self, client):
        """Security 2: لا فرق في الرسالة أو الكود بين بريد غير موجود وكلمة
        مرور خاطئة — يمنع اكتشاف وجود الحساب (user enumeration)."""
        res = client.post("/api/auth/login", json={
            "email": "does-not-exist@test.com",
            "password": "Whatever123!",
        })
        assert res.status_code == 401
        assert res.json()["error_code"] == "INVALID_CREDENTIALS"


# ══════════════════════════════════════════════════════
#  2. نسيت كلمة المرور → OTP → إعادة التعيين
# ══════════════════════════════════════════════════════
class TestForgotPasswordFlow:
    def _register_and_get_otp(self, client):
        client.post("/api/auth/register", json={
            "name": "نسيان",
            "email": "forgot@test.com",
            "password": "OldPass123!",
        })

        res = client.post("/api/auth/forgot-password", json={
            "email": "forgot@test.com",
        })
        assert res.status_code == 200
        return res

    def test_forgot_password_always_returns_200(self, client):
        res = client.post("/api/auth/forgot-password", json={
            "email": "nonexistent@test.com",
        })
        assert res.status_code == 200
        assert "ستصله رسالة" in res.json()["message"]

    def test_verify_otp_with_correct_code(self, client, db_session):
        self._register_and_get_otp(client)

        from app.database import PasswordResetOTP
        from app.auth import hash_password
        otp_code = "123456"
        otp_record = PasswordResetOTP(
            email="forgot@test.com",
            otp_hash=hash_password(otp_code),
            expires_at=datetime(2099, 1, 1),
        )
        db_session.add(otp_record)
        db_session.commit()

        res = client.post("/api/auth/verify-otp", json={
            "email": "forgot@test.com",
            "otp": otp_code,
        })
        assert res.status_code == 200
        assert "reset_token" in res.json()

    def test_verify_otp_wrong_code(self, client, db_session):
        self._register_and_get_otp(client)

        from app.database import PasswordResetOTP
        from app.auth import hash_password
        otp_record = PasswordResetOTP(
            email="forgot@test.com",
            otp_hash=hash_password("111111"),
            expires_at=datetime(2099, 1, 1),
        )
        db_session.add(otp_record)
        db_session.commit()

        res = client.post("/api/auth/verify-otp", json={
            "email": "forgot@test.com",
            "otp": "999999",
        })
        assert res.status_code == 400
        assert res.json()["error_code"] == "OTP_INVALID"

    def test_full_reset_flow(self, client, db_session):
        self._register_and_get_otp(client)

        from app.database import PasswordResetOTP
        from app.auth import hash_password, create_password_reset_token
        from app.database import User

        otp_code = "555555"
        otp_record = PasswordResetOTP(
            email="forgot@test.com",
            otp_hash=hash_password(otp_code),
            expires_at=datetime(2099, 1, 1),
        )
        db_session.add(otp_record)
        db_session.commit()

        res = client.post("/api/auth/verify-otp", json={
            "email": "forgot@test.com",
            "otp": otp_code,
        })
        reset_token = res.json()["reset_token"]

        res = client.post("/api/auth/reset-password", json={
            "reset_token": reset_token,
            "new_password": "NewPass123!",
        })
        assert res.status_code == 200
        assert "تم تغيير كلمة المرور" in res.json()["message"]

        client.cookies.clear()
        res = client.post("/api/auth/login", json={
            "email": "forgot@test.com",
            "password": "OldPass123!",
        })
        assert res.status_code == 401

        res = client.post("/api/auth/login", json={
            "email": "forgot@test.com",
            "password": "NewPass123!",
        })
        assert res.status_code == 200


# ══════════════════════════════════════════════════════
#  3. دوران توكن التحديث (Refresh Token Rotation)
# ══════════════════════════════════════════════════════
class TestRefreshTokenRotation:
    def test_refresh_rotates_token(self, client):
        client.post("/api/auth/register", json={
            "name": "دوران",
            "email": "rotate@test.com",
            "password": "Pass1234!",
        })
        old_refresh = client.cookies.get("sawa_refresh")

        res = client.post("/api/auth/refresh")
        assert res.status_code == 200
        new_refresh = client.cookies.get("sawa_refresh")
        assert new_refresh != old_refresh

        res2 = client.get("/api/auth/me")
        assert res2.status_code == 200

    def test_old_refresh_token_revoked(self, client):
        client.post("/api/auth/register", json={
            "name": "إلغاء",
            "email": "revoke@test.com",
            "password": "Pass1234!",
        })
        old_refresh = client.cookies.get("sawa_refresh")
        client.post("/api/auth/refresh")

        from app.database import SessionLocal, RefreshToken
        from app.auth import hash_token
        db = SessionLocal()
        token_record = db.query(RefreshToken).filter(
            RefreshToken.token_hash == hash_token(old_refresh)
        ).first()
        assert token_record is not None
        assert token_record.revoked is True
        db.close()

    def test_refresh_returns_access_token_in_body(self, client):
        client.post("/api/auth/register", json={
            "name": "توكن التحديث",
            "email": "refresh-token@test.com",
            "password": "Pass1234!",
        })
        res = client.post("/api/auth/refresh")
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body and body["access_token"]
        assert body["token_type"] == "bearer"

    def test_refresh_without_cookie_returns_401(self, client):
        client.post("/api/auth/register", json={
            "name": "بدون",
            "email": "nocookie@test.com",
            "password": "Pass1234!",
        })
        client.cookies.clear()
        res = client.post("/api/auth/refresh")
        assert res.status_code == 401
        assert res.json()["error_code"] == "TOKEN_EXPIRED"


# ══════════════════════════════════════════════════════
#  4. تغيير كلمة المرور مع التحقق من الصحة
# ══════════════════════════════════════════════════════
class TestPasswordChange:
    def test_change_password_success(self, client):
        client.post("/api/auth/register", json={
            "name": "تغيير",
            "email": "change@test.com",
            "password": "OldPass123!",
        })
        res = client.patch("/api/auth/settings/password", json={
            "current_password": "OldPass123!",
            "new_password": "NewPass456!",
        })
        assert res.status_code == 200

        client.cookies.clear()
        res = client.post("/api/auth/login", json={
            "email": "change@test.com",
            "password": "NewPass456!",
        })
        assert res.status_code == 200

    def test_wrong_current_password(self, client):
        client.post("/api/auth/register", json={
            "name": "خطأ",
            "email": "wrongcurr@test.com",
            "password": "RealPass123!",
        })
        res = client.patch("/api/auth/settings/password", json={
            "current_password": "WrongPass!",
            "new_password": "NewPass456!",
        })
        assert res.status_code == 401
        assert res.json()["error_code"] == "WRONG_PASSWORD"

    def test_same_password_rejected(self, client):
        client.post("/api/auth/register", json={
            "name": "مطابق",
            "email": "same@test.com",
            "password": "SamePass123!",
        })
        res = client.patch("/api/auth/settings/password", json={
            "current_password": "SamePass123!",
            "new_password": "SamePass123!",
        })
        assert res.status_code == 400
        assert res.json()["error_code"] == "SAME_PASSWORD"

    def test_short_password_rejected(self, client):
        client.post("/api/auth/register", json={
            "name": "قصير",
            "email": "short@test.com",
            "password": "LongPass123!",
        })
        res = client.patch("/api/auth/settings/password", json={
            "current_password": "LongPass123!",
            "new_password": "Ab1",
        })
        assert res.status_code == 422

    def test_password_without_digit_rejected(self, client):
        client.post("/api/auth/register", json={
            "name": "رقم",
            "email": "nodigit@test.com",
            "password": "Digit1234!",
        })
        res = client.patch("/api/auth/settings/password", json={
            "current_password": "Digit1234!",
            "new_password": "NoDigitHere!",
        })
        assert res.status_code == 422

    def test_change_password_revokes_all_refresh_tokens(self, client):
        client.post("/api/auth/register", json={
            "name": "إلغاء الكل",
            "email": "revokeall@test.com",
            "password": "Pass1234!",
        })
        client.patch("/api/auth/settings/password", json={
            "current_password": "Pass1234!",
            "new_password": "NewPass567!",
        })

        from app.database import SessionLocal, RefreshToken
        db = SessionLocal()
        active = db.query(RefreshToken).filter(
            RefreshToken.user_id == db.query(RefreshToken).first().user_id,
            RefreshToken.revoked == False,
        ).count()
        db.close()
        assert active == 0


# ══════════════════════════════════════════════════════
#  5. إعدادات المستخدم (الاسم + CSRF)
# ══════════════════════════════════════════════════════
class TestUserSettings:
    def test_update_name(self, client):
        client.post("/api/auth/register", json={
            "name": "الاسم القديم",
            "email": "name@test.com",
            "password": "Pass1234!",
        })
        res = client.patch("/api/auth/settings/name", json={
            "name": "الاسم الجديد",
        })
        assert res.status_code == 200
        assert res.json()["name"] == "الاسم الجديد"

    def test_csrf_token_endpoint(self, client):
        res = client.get("/api/auth/csrf-token")
        assert res.status_code == 200
        assert "csrf_token" in res.json()
        assert len(res.json()["csrf_token"]) > 10

    def test_settings_require_auth(self, client):
        client.cookies.clear()
        res = client.patch("/api/auth/settings/name", json={
            "name": "بلا توكن",
        })
        assert res.status_code == 401

    def test_name_too_short(self, client):
        client.post("/api/auth/register", json={
            "name": "اسم عادي",
            "email": "longname@test.com",
            "password": "Pass1234!",
        })
        res = client.patch("/api/auth/settings/name", json={
            "name": "أ",
        })
        assert res.status_code == 422
