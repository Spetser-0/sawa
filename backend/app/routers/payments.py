"""
نظام الاشتراكات والمدفوعات — Cryptomus
"""
import hmac
import hashlib
import json
import base64
import re
import httpx
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db, User
from app.auth import require_auth

router = APIRouter()

# ── إعدادات Cryptomus ────────────────────────────────
CRYPTOMUS_API_KEY    = os.getenv("CRYPTOMUS_API_KEY", "")
CRYPTOMUS_MERCHANT   = os.getenv("CRYPTOMUS_MERCHANT_ID", "")
CRYPTOMUS_BASE_URL   = "https://api.cryptomus.com/v1"

# ── خطط الاشتراك ─────────────────────────────────────
PLANS = {
    "free": {
        "name":          "مجاني",
        "price_usd":     0,
        "max_videos":    25,
        "max_duration":  300,    # 5 دقائق
        "features":      ["25 تسجيل", "5 دقائق للمقطع", "تفريغ أساسي"],
    },
    "pro": {
        "name":          "Pro",
        "price_usd":     7,
        "max_videos":    9999,
        "max_duration":  3600,   # ساعة
        "features":      ["غير محدود", "ساعة كاملة", "ترجمة + تلخيص AI", "تصدير DOCX"],
    },
    "team": {
        "name":          "Team",
        "price_usd":     20,
        "max_videos":    9999,
        "max_duration":  7200,   # ساعتان
        "features":      ["كل مزايا Pro", "5 أعضاء", "Workspace مشترك", "API Access"],
    },
}


# ══════════════════════════════════════════════════════
#  GET /api/payments/plans  — عرض الخطط
# ══════════════════════════════════════════════════════
@router.get("/plans")
def get_plans():
    return PLANS


# ══════════════════════════════════════════════════════
#  GET /api/payments/status  — حالة اشتراك المستخدم
# ══════════════════════════════════════════════════════
@router.get("/status")
def get_subscription_status(
    current_user: User    = Depends(require_auth),
    db:           Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == current_user.id).first()
    plan = PLANS.get(user.plan, PLANS["free"])

    is_active  = True
    days_left  = None
    expired    = False

    if user.subscription_expires_at:
        remaining  = user.subscription_expires_at - datetime.now(timezone.utc).replace(tzinfo=None)
        days_left  = max(0, remaining.days)
        expired    = remaining.total_seconds() <= 0
        is_active  = not expired

    return {
        "plan":        user.plan,
        "plan_name":   plan["name"],
        "is_active":   is_active,
        "expires_at":  user.subscription_expires_at,
        "days_left":   days_left,
        "expired":     expired,
        "features":    plan["features"],
        "limits": {
            "max_videos":   plan["max_videos"],
            "max_duration": plan["max_duration"],
        }
    }


# ══════════════════════════════════════════════════════
#  POST /api/payments/create  — إنشاء رابط دفع
# ══════════════════════════════════════════════════════
class CreatePaymentRequest(BaseModel):
    plan: str  # "pro" | "team"

@router.post("/create")
async def create_payment(
    data:         CreatePaymentRequest,
    current_user: User    = Depends(require_auth),
    db:           Session = Depends(get_db),
):
    if data.plan not in ["pro", "team"]:
        raise HTTPException(400, "خطة غير صحيحة")

    plan = PLANS[data.plan]

    # ── بناء طلب Cryptomus ──────────────────────────
    payload = {
        "amount":      str(plan["price_usd"]),
        "currency":    "USD",
        "order_id":    f"{current_user.id}_{data.plan}_{int(datetime.now(timezone.utc).replace(tzinfo=None).timestamp())}",
        "url_success": f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/dashboard?payment=success",
        "url_callback": f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/api/payments/webhook",
        "is_payment_multiple": False,
        "lifetime":    3600,  # رابط صالح ساعة
        # بيانات مخصصة لمعرفة من دفع
        "additional_data": json.dumps({
            "user_id":  current_user.id,
            "user_email": current_user.email,
            "plan":     data.plan,
        }),
    }

    # إذا لم يكن Cryptomus مضبوطاً — وضع تطوير
    if not CRYPTOMUS_API_KEY:
        return {
            "mode":      "development",
            "message":   "Cryptomus غير مضبوط — وضع التطوير",
            "plan":      data.plan,
            "price":     plan["price_usd"],
            "demo_url":  f"http://localhost:3000/dashboard?payment=demo&plan={data.plan}",
            "instructions": "أضف CRYPTOMUS_API_KEY و CRYPTOMUS_MERCHANT_ID في .env",
        }

    # ── إرسال الطلب لـ Cryptomus ────────────────────
    body_str  = base64.b64encode(json.dumps(payload).encode()).decode()
    signature = hashlib.md5(f"{body_str}{CRYPTOMUS_API_KEY}".encode()).hexdigest()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{CRYPTOMUS_BASE_URL}/payment",
                headers={
                    "merchant": CRYPTOMUS_MERCHANT,
                    "sign":     signature,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            resp_data = resp.json()
            if resp.status_code == 200 and resp_data.get("state") == 0:
                return {
                    "payment_url": resp_data["result"]["url"],
                    "order_id":    resp_data["result"]["order_id"],
                    "amount":      plan["price_usd"],
                    "plan":        data.plan,
                }
            raise HTTPException(400, f"فشل إنشاء رابط الدفع: {resp_data.get('message','')}")
        except httpx.TimeoutException:
            raise HTTPException(503, "انتهت مهلة الاتصال بـ Cryptomus")


def _strip_sign_field(raw: bytes) -> Optional[bytes]:
    """يحذف حقل 'sign' من نص JSON الخام دون إعادة تسلسل باقي الحقول — لتفادي
    أي اختلاف في ترتيب المفاتيح، الفراغات، أو ترميز الأرقام/اليونيكود قد
    يكسر التحقق من التوقيع (وهو بالضبط الخلل في التطبيق القديم الذي كان
    يعيد بناء JSON من القاموس المُحلَّل بدل الاعتماد على البايتات الخام)."""
    text = raw.decode("utf-8")
    m = re.search(r'"sign"\s*:\s*"(?:[^"\\]|\\.)*"', text)
    if not m:
        return None
    start, end = m.span()
    before = text[:start].rstrip()
    after = text[end:].lstrip()
    if before.endswith(","):
        before = before[:-1]
    elif after.startswith(","):
        after = after[1:]
    return (before + after).encode("utf-8")


# ══════════════════════════════════════════════════════
#  POST /api/payments/webhook  — استقبال تأكيد الدفع
# ══════════════════════════════════════════════════════
@router.post("/webhook")
async def payment_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Cryptomus يستدعي هذا الـ endpoint تلقائياً بعد أي دفع.

    أمان: التوقيع يُحسب على البايتات الخام للطلب (بعد حذف حقل sign فقط)،
    وليس على إعادة تسلسل القاموس المُحلَّل — لأن أي اختلاف بسيط في ترتيب
    المفاتيح أو تنسيق الأرقام كان يكسر المقارنة سابقاً بشكل غير موثوق.
    لا نُعالج أي بيانات من additional_data (مثل user_id) قبل التأكد من
    صحة التوقيع أولاً.
    """
    if not CRYPTOMUS_API_KEY:
        # عدم ضبط المفتاح لا يعني تخطي التحقق — يعني رفض الطلب بالكامل
        raise HTTPException(503, "بوابة الدفع غير مُهيّأة على الخادم")

    body = await request.body()

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "جسم الطلب غير صالح")

    received_sign = data.get("sign", "")
    body_without_sign = _strip_sign_field(body)
    if body_without_sign is None or not received_sign:
        raise HTTPException(401, "توقيع مفقود")

    body_str = base64.b64encode(body_without_sign).decode()
    expected_sign = hashlib.md5(f"{body_str}{CRYPTOMUS_API_KEY}".encode()).hexdigest()

    if not hmac.compare_digest(received_sign, expected_sign):
        raise HTTPException(401, "توقيع غير صحيح")

    # ── من هنا فقط يُعتبر الطلب موثوقاً — التوقيع تحقق بنجاح ──
    data.pop("sign", None)

    # ── تحقق من حالة الدفع ──────────────────────────
    pay_status = data.get("status", "")
    if pay_status not in ["paid", "paid_over"]:
        # دفع ناقص أو في الانتظار — لا تفعّل الاشتراك
        return {"message": f"الحالة: {pay_status} — لم يُفعَّل الاشتراك بعد"}

    # ── استخرج بيانات المستخدم ──────────────────────
    try:
        extra = json.loads(data.get("additional_data", "{}"))
    except json.JSONDecodeError:
        extra = {}

    user_id = extra.get("user_id")
    plan    = extra.get("plan", "pro")

    if not user_id:
        raise HTTPException(400, "لا يوجد user_id")

    # ── فعّل الاشتراك ────────────────────────────────
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "المستخدم غير موجود")

    user.plan = plan
    user.subscription_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
    db.commit()

    # ── سجّل عملية الدفع ─────────────────────────────
    _log_payment(db, user_id, plan, data.get("amount", "0"), data.get("order_id", ""))

    return {"message": "تم تفعيل الاشتراك بنجاح ✅"}


# ══════════════════════════════════════════════════════
#  POST /api/payments/demo-activate  — تفعيل تجريبي (للتطوير)
# ══════════════════════════════════════════════════════
@router.post("/demo-activate/{plan}")
def demo_activate(
    plan:         str,
    current_user: User    = Depends(require_auth),
    db:           Session = Depends(get_db),
):
    """
    تفعيل اشتراك تجريبي بدون دفع فعلي — للتطوير فقط
    احذف هذا الـ endpoint قبل الإنتاج!
    """
    if os.getenv("ENVIRONMENT") == "production":
        raise HTTPException(403, "غير متاح في الإنتاج")

    if plan not in PLANS:
        raise HTTPException(400, "خطة غير صحيحة")

    user = db.query(User).filter(User.id == current_user.id).first()
    user.plan = plan
    user.subscription_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
    db.commit()

    return {
        "message": f"✅ تم تفعيل خطة {PLANS[plan]['name']} تجريبياً لمدة 30 يوم",
        "expires_at": user.subscription_expires_at,
    }


# ══════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════
def _log_payment(db, user_id, plan, amount, order_id):
    """سجّل عمليات الدفع للمراجعة لاحقاً"""
    import logging
    logging.getLogger(__name__).info(
        f"💰 دفع مكتمل | user={user_id} | plan={plan} | amount={amount}$ | order={order_id}"
    )
