"""
إعداد قاعدة البيانات ونماذج الجداول
"""
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone
import enum
import uuid

from app.config import settings

def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

# ── إعداد المحرك ─────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    # مطلوب لـ SQLite فقط
    connect_args={
        "check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── Dependency لجلسة قاعدة البيانات ─────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ══════════════════════════════════════════════════════
#  ENUMS
# ══════════════════════════════════════════════════════
class TranscriptStatus(str, enum.Enum):
    PENDING = "pending"     # في الانتظار
    DENOISING = "denoising"   # جاري تنظيف الصوت
    PROCESSING = "processing"  # قيد المعالجة
    DONE = "done"        # اكتمل
    FAILED = "failed"      # فشل


class UserPlan(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"


class ArabicDialect(str, enum.Enum):
    STANDARD = "ar"       # عربي فصحى
    EGYPTIAN = "ar-EG"    # مصري
    GULF = "ar-AE"    # خليجي
    LEVANTINE = "ar-SY"    # شامي
    MAGHREBI = "ar-MA"    # مغاربي
    LIBYAN = "ar-LY"    # ليبي


# ══════════════════════════════════════════════════════
#  MODELS
# ══════════════════════════════════════════════════════
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    plan = Column(String, default=UserPlan.FREE)
    is_active = Column(Boolean, default=True)
    subscription_expires_at = Column(DateTime, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    # علاقة: مستخدم → فيديوهاته
    videos = relationship("Video", back_populates="owner",
                          cascade="all, delete")
    refresh_tokens = relationship("RefreshToken", back_populates="user",
                                  cascade="all, delete")

    def __repr__(self):
        return f"<User {self.email} [{self.plan}]>"


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False, default="تسجيل جديد")
    description = Column(Text, nullable=True)

    # ── الملف ──────────────────────────────────────
    file_path = Column(String, nullable=False)   # مسار الملف المحلي أو URL
    file_size = Column(Integer, nullable=True)   # بالبايت
    duration = Column(Float, nullable=True)     # بالثواني
    mime_type = Column(String, nullable=True)

    # ── إعدادات التفريغ ─────────────────────────────
    dialect = Column(String, default=ArabicDialect.STANDARD)
    is_public = Column(Boolean, default=False)   # رابط المشاركة العام — خصوصي افتراضياً
    share_token = Column(String, unique=True, default=lambda: uuid.uuid4().hex)

    # ── مشاركة محمية ───────────────────────────────
    share_password_hash = Column(String, nullable=True)
    share_expires_at = Column(DateTime, nullable=True)

    # ── HLS ─────────────────────────────────────────
    hls_ready = Column(Boolean, default=False)
    hls_playlist_path = Column(String, nullable=True)

    # ── الصورة المصغرة ─────────────────────────────
    thumbnail_path = Column(String, nullable=True)

    # ── الحالة ──────────────────────────────────────
    status = Column(String, default="uploaded")

    # ── البيانات الوصفية ─────────────────────────────
    views_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow,
                        onupdate=_utcnow)

    # ── العلاقات ─────────────────────────────────────
    owner_id = Column(String, ForeignKey("users.id"),
                      nullable=True)  # nullable للزوار
    owner = relationship("User", back_populates="videos")
    transcript = relationship(
        "Transcript", back_populates="video", uselist=False, cascade="all, delete")
    comments = relationship("Comment", back_populates="video",
                            cascade="all, delete")
    view_events = relationship("ViewEvent", back_populates="video",
                               cascade="all, delete")

    def __repr__(self):
        return f"<Video '{self.title}' [{self.id[:8]}]>"


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id = Column(String, ForeignKey("videos.id"),
                      unique=True, nullable=False)

    # ── النتائج ──────────────────────────────────────
    full_text = Column(Text, nullable=True)           # النص الكامل
    # JSON: [{start, end, text}, ...]
    segments_json = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)           # ملخص AI (مرحلة لاحقة)
    chapters_json = Column(Text, nullable=True)     # فصول ذكية [{start, end, title, summary}]

    # ── الحالة ───────────────────────────────────────
    status = Column(String, default=TranscriptStatus.PENDING)
    error_message = Column(Text, nullable=True)
    language_detected = Column(String, nullable=True)   # ما اكتشفه Whisper

    # ── التوقيت ──────────────────────────────────────
    processing_time = Column(Float, nullable=True)      # ثواني استغرق التفريغ
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow,
                        onupdate=_utcnow)

    # ── العلاقة ──────────────────────────────────────
    video = relationship("Video", back_populates="transcript")

    def __repr__(self):
        return f"<Transcript video={self.video_id[:8]} status={self.status}>"


class Comment(Base):
    __tablename__ = "comments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id = Column(String, ForeignKey("videos.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    timestamp_seconds = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    author_name = Column(String, default="زائر")
    created_at = Column(DateTime, default=_utcnow)

    video = relationship("Video", back_populates="comments")

    def __repr__(self):
        return f"<Comment {self.author_name} @{self.timestamp_seconds}s>"


class ViewEvent(Base):
    __tablename__ = "view_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id = Column(String, ForeignKey("videos.id"), nullable=False, index=True)
    viewer_ip_hash = Column(String, nullable=True)
    country = Column(String, nullable=True)
    watch_duration_seconds = Column(Integer, default=0)
    watched_at = Column(DateTime, default=_utcnow)

    video = relationship("Video", back_populates="view_events")

    def __repr__(self):
        return f"<ViewEvent video={self.video_id[:8]} country={self.country}>"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken user={self.user_id[:8]} revoked={self.revoked}>"


class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otps"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, index=True)
    otp_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)

    def __repr__(self):
        return f"<PasswordResetOTP email={self.email} used={self.used}>"
