from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Numeric, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
import random
from fastapi import APIRouter, HTTPException, status, Depend, Request
from datetime import datetime, timedelta
from jose import jwt
import uuid
import httpx # برای ارسال درخواست به SMS.ir
# --- تنظیمات دیتابیس (فرض بر استفاده از MySQL طبق درخواست قبلی تو) ---
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://user:password@localhost/dbname"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

app = FastAPI()

# --- مدل‌های دیتابیس اصلاح شده ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True)
    balance = Column(Numeric(12, 2), default=0.0)

class Room(Base):
    __tablename__ = "rooms"
    id = Column(String, primary_key=True, index=True)
    status = Column(String, default="waiting")  # waiting, playing, finished
    total_rounds_required = Column(Integer, default=5)
    total_prize_pool = Column(Numeric(12, 2), default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    game_start_time = Column(DateTime, nullable=True)
    participants = relationship("RoomParticipant", back_populates="room")

class RoomParticipant(Base):
    __tablename__ = "room_participants"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # پیشرفت هر کاربر به صورت جداگانه مدیریت می‌شود
    current_progress = Column(Integer, default=0) 
    is_eliminated = Column(Boolean, default=False)
    
    room = relationship("Room", back_populates="participants")
    user = relationship("User")
class RoomRound(Base):
    """ذخیره اعداد درست برای هر راند در هر اتاق"""
    __tablename__ = "room_rounds"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))
    round_number = Column(Integer) # شماره راند (۱، ۲، ۳، ...)
    correct_answer = Column(Integer) # عدد درست برای این راند

    room = relationship("Room")

# --- توابع کمکی (Helper Functions) ---


# فرض می‌کنیم این‌ها از فایل مدل‌ها و تنظیمات شما وارد می‌شوند
# from database import get_db, User, UserSession, pwd_context, SECRET_KEY, ALGORITHM

router = APIRouter()

# --- Pydantic Schemas ---
class UserRegisterSchema(Base):
    phone: str
    password: str
    name: Optional[str] = None

class UserLoginSchema(Base):
    phone: str
    password: str
    device_info: Optional[str] = "Unknown Device"

class TokenResponse(Base):
    access_token: str
    refresh_token: str
    token_type: str


# فرض بر این است که مدل‌ها و تنظیمات قبلی ایمپورت شده‌اند
# from database import User, UserSession, OTPCode, db_session, pwd_context, SECRET_KEY, ALGORITHM



# --- تنظیمات SMS.ir (حتماً در Environment Variables قرار دهید) ---
SMS_USERNAME = os.getenv("SMS_USERNAME")
SMS_PASSWORD = os.getenv("SMS_PASSWORD")
SMS_LINE = os.getenv("SMS_LINE")

# --- Schemas ---
class OTPRequestSchema(Base):
    phone: str

class OTPVerifySchema(Base):
    phone: str
    code: str
    device_info: Optional[str] = "Unknown Device"
# --- Schemas برای فراموشی رمز ---
class ForgotPasswordRequestSchema(Base):
    phone: str

class ResetPasswordSchema(Base):
    phone: str
    code: str
    new_password: str

# --- Routes برای فراموشی رمز ---

@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequestSchema, db: Session = Depends(get_db)):
    """
    مرحله ۱: کاربر شماره موبایل را می‌دهد و کد تایید برایش ارسال می‌شود
    """
    # ۱. بررسی اینکه آیا اصلاً کاربری با این شماره وجود دارد یا خیر
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user:
        # برای امنیت بیشتر، حتی اگر کاربر وجود نداشت هم پیام موفقیت بدهیم 
        # تا هکرها نتوانند با تست کردن شماره‌ها بفهمند چه کسی در سایت عضو است.
        return {"message": "اگر این شماره در سیستم باشد، کد ارسال خواهد شد."}

    # ۲. تولید کد OTP (دقیقاً مثل فرآیند ثبت‌نام)
    otp_code = str(random.randint(1000, 9999))
    
    # ذخیره در دیتابیس (اگر از قبل بود آپدیت شود)
    existing_otp = db.query(OTPCode).filter(OTPCode.phone == data.phone).first()
    if existing_otp:
        existing_otp.code = otp_code
        existing_otp.expires_at = datetime.utcnow() + timedelta(minutes=2)
    else:
        new_otp = OTPCode(
            phone=data.phone,
            code=otp_code,
            expires_at=datetime.utcnow() + timedelta(minutes=2)
        )
        db.add(new_otp)
    
    db.commit()

    # ۳. ارسال پیامک
    sms_sent = await send_sms_otp(data.phone, otp_code)
    
    if not sms_sent:
        raise HTTPException(status_code=500, detail="خطا در ارسال پیامک.")

    return {"message": "کد تایید برای بازنشانی رمز عبور ارسال شد."}

@router.post("/auth/reset-password")
async def reset_password(data: ResetPasswordSchema, db: Session = Depends(get_db)):
    """
    مرحله ۲ و ۳: تایید کد و تغییر رمز عبور جدید
    """
    # ۱. بررسی وجود کاربر
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="کاربری با این شماره یافت نشد.")

    # ۲. تایید صحت کد OTP
    otp_record = db.query(OTPCode).filter(
        OTPCode.phone == data.phone, 
        OTPCode.code == data.code
    ).first()

    if not otp_record or otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="کد تایید اشتباه یا منقضی شده است.")

    # ۳. هش کردن پسورد جدید
    ******* = pwd_context.hash(user_data.password) # pwd_context.hash

    # ۴. آپدیت پسورد کاربر
    try:
        user.password = *******
        
        # ۵. پاک کردن کد OTP از دیتابیس برای امنیت بیشتر
        db.delete(otp_record)
        
        # ۶. (اختیاری اما مهم) غیرفعال کردن تمام نشست‌های قبلی کاربر
        # چون رمز عوض شده، کاربر باید در تمام دستگاه‌ها دوباره لاگین کند
        db.query(UserSession).filter(UserSession.user_id == user.id).update({"is_active": False})
        
        db.commit()
        return {"message": "رمز عبور با موفقیت تغییر یافت. اکنون می‌توانید وارد شوید."}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="خطا در تغییر رمز عبور.")

# --- Helper Functions ---

async def send_sms_otp(phone: str, code: str):
    """
    ارسال کد از طریق سرویس SMS.ir
    """
    url = "https://api.sms.ir/v1/send/text" # آدرس API را چک کنید
    payload = {
        "username": SMS_USERNAME,
        "password": SMS_PASSWORD,
        "recipient": phone,
        "text": f"کد تایید شما: {code}"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=5.0)
            return response.status_code == 200
    except Exception:
        return False

# --- Routes ---

@router.post("/auth/request-otp")
async def request_otp(data: OTPRequestSchema, db: Session = Depends(get_db)):
    """
    مرحله اول: درخواست کد تایید برای شماره موبایل
    """
    # ۱. تولید کد ۴ یا ۵ رقمی
    otp_code = str(random.randint(1000, 9999))
    
    # ۲. ذخیره در دیتابیس (اگر از قبل بود، آپدیت شود)
    existing_otp = db.query(OTPCode).filter(OTPCode.phone == data.phone).first()
    
    if existing_otp:
        existing_otp.code = otp_code
        existing_otp.expires_at = datetime.utcnow() + timedelta(minutes=2)
    else:
        new_otp = OTPCode(
            phone=data.phone,
            code=otp_code,
            expires_at=datetime.utcnow() + timedelta(minutes=2)
        )
        db.add(new_otp)
    
    db.commit()

    # ۳. ارسال پیامک
    sms_sent = await send_sms_otp(data.phone, otp_code)
    
    if not sms_sent:
        # در محیط تست ممکن است SMS کار نکند، اما در محیط واقعی خطا بدهد
        raise HTTPException(status_code=500, detail="خطا در ارسال پیامک. لطفا دوباره تلاش کنید.")

    return {"message": "کد تایید ارسال شد."}

@router.post("/auth/verify-otp")
async def verify_otp(data: OTPVerifySchema, db: Session = Depends(get_db), request: Request = None):
    """
    مرحله دوم: تایید کد و ورود یا ثبت‌نام نهایی
    """
    # ۱. پیدا کردن کد در دیتابیس
    otp_record = db.query(OTPCode).filter(
        OTPCode.phone == data.phone, 
        OTPCode.code == data.code
    ).first()

    # ۲. بررسی صحت کد و انقضا
    if not otp_record or otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="کد وارد شده اشتباه یا منقضی شده است.")

    # ۳. بررسی اینکه کاربر وجود دارد یا باید ساخته شود
    user = db.query(User).filter(User.phone == data.phone).first()
    
    if not user:
        # کاربر جدید است -> ثبت‌نام
        user = User(
            phone=data.phone,
            password=*******, # پسورد پیش‌فرض یا تولید شده رندوم برای OTP
            name=None # کاربر بعداً می‌تواند نام را در پروفایل ست کند
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # ۴. پاک کردن کد OTP از دیتابیس برای جلوگیری از استفاده مجدد
    db.delete(otp_record)
    db.commit()

    # ۵. تولید توکن‌ها (Access & Refresh)
    # همان منطقی که در پاسخ قبلی نوشتم را اینجا اجرا می‌کنیم
    access_token, refresh_token = generate_token_pair(user.id) # تابع کمکی فرضی

    # ۶. ذخیره نشست (Session)
    new_session = UserSession(
        user_id=user.id,
        refresh_token=refresh_token,
        device_info=data.device_info,
        ip_address=request.client.host if request else "0.0.0.0",
        is_active=True
    )
    db.add(new_session)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

# تابع کمکی برای تولید توکن (برای جلوگیری از تکرار کد)
def generate_token_pair(user_id: int):
    # Access Token
    access_expire = datetime.utcnow() + timedelta(minutes=60)
    access_payload = {"sub": str(user_id), "exp": access_expire, "type": "access"}
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    # Refresh Token
    refresh_token = refresh_token_str(uuid.uuid4())
    refresh_expire = datetime.utcnow() + timedelta(days=30)
    refresh_payload = {"sub": str(user_id), "exp": refresh_expire, "type": "refresh", "jti": refresh_token}
    refresh_token_jwt = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    return access_token, refresh_token

# --- Implementation ---

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegisterSchema, db: Session = Depends(get_db)):
    """
    ثبت‌نام کاربر جدید
    """
    # ۱. بررسی اینکه آیا کاربر قبلاً ثبت‌نام کرده یا خیر
    existing_user = db.query(User).filter(User.phone == user_data.phone).first()
    if existing_user:
        raise HTTPException(
            status_code=400, 
            detail="این شماره موبایل قبلاً ثبت شده است."
        )

    # ۲. هش کردن رمز عبور
    hashed_password = pwd_context.hash(user_data.password)

    # ۳. ایجاد کاربر جدید
    new_user = User(
        phone=user_data.phone,
        password=hashed_password,
        name=user_data.name,
        wallet_balance=0 # مقدار اولیه موجودی
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"message": "ثبت‌نام با موفقیت انجام شد.", "user_id": new_user.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="خطا در ثبت‌نام کاربر.")

@router.post("/login", response_model=TokenResponse)
async def login(login_data: UserLoginSchema, db: Session = Depends(get_db)):
    """
    ورود کاربر و تولید توکن‌های دسترسی
    """
    # ۱. پیدا کردن کاربر
    user = db.query(User).filter(User.phone == login_data.phone).first()
    
    # ۲. بررسی وجود کاربر و صحت پسورد
    if not user or not pwd_context.verify(login_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="شماره موبایل یا رمز عبور اشتباه است."
        )

    # ۳. تولید توکن‌ها
    # ایجاد Access Token
    access_expire = datetime.utcnow() + timedelta(minutes=60) # ۶۰ دقیقه اعتبار
    access_payload = {
        "sub": str(user.id),
        "exp": access_expire,
        "type": "access"
    }
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    # ایجاد Refresh Token (یک رشته تصادفی منحصر به فرد)
    refresh_token_str = str(uuid.uuid4())
    refresh_expire = datetime.utcnow() + timedelta(days=30) # ۳۰ روز اعتبار
    
    refresh_payload = {
        "sub": str(user.id),
        "exp": refresh_expire,
        "type": "refresh",
        "jti": refresh_token_str # استفاده از jti برای شناسایی توکن در دیتابیس
    }
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    # ۴. ذخیره نشست (Session) در دیتابیس برای قابلیت Revoke
    new_session = UserSession(
        user_id=user.id,
        refresh_token=refresh_token_str, # ذخیره شناسه توکن برای چک کردن در آینده
        device_info=login_data.device_info,
        ip_address="127.0.0.1", # در واقعیت از request.client.host بگیرید
        is_active=True
    )
    
    try:
        db.add(new_session)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="خطا در ایجاد نشست کاربر.")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/logout")
async def logout(current_user_id: int, db: Session = Depends(get_db)):
    """
    خروج از حساب (غیرفعال کردن نشست فعلی)
    """
    # پیدا کردن آخرین نشست فعال کاربر و غیرفعال کردن آن
    session = db.query(UserSession).filter(
        UserSession.user_id == current_user_id,
        UserSession.is_active == True
    ).order_by(UserSession.last_used_at.desc()).first()

    if session:
        session.is_active = False
        db.commit()
        return {"message": "خروج با موفقیت انجام شد."}
    
    raise HTTPException(status_code=404, detail="نشستی یافت نشد.")

def get_target_for_round(round_number: int) -> int:
    """
    این تابع تعیین می‌کند در هر راند، عدد درست چه باشد.
    برای اینکه همه در یک راند هدف مشترک داشته باشند، از یک فرمول یا Seed استفاده می‌کنیم.
    """
    random.seed(round_number) # ثابت نگه داشتن عدد برای همه در یک راند مشخص
    return random.randint(1, 100)

async def distribute_prize(winner_id: int, room_id: str, db: Session=Depends(get_db)):
    """
    پرداخت جایزه به برنده و کسر از استخر جایزه.
    این تابع باید بسیار امن باشد.
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    winner = db.query(User).filter(User.id == winner_id).first()
    
    if room and winner:
        prize_amount = ((room.total_prize_pool // 100)*60)  # ۶۰ درصد برای برنده
        winner.balance += prize_amount
        db.commit()
        # ۴۰ درصد باقی‌مانده به عنوان کارمزد سیستم در دیتابیس باقی می‌ماند
        print(f"Winner {winner_id} received {prize_amount}")
# فرض کن این تابع هنگام ساخت اتاق اجرا می‌شود
def setup_room_rounds(db: Session=Depends(get_db), room_id: str, total_rounds: int):
    for r in range(1, total_rounds + 1):
        # اینجا می‌توانی اعداد را از یک لیست مشخص یا تصادفی برداری
        correct_val = random.randint(1, 100) 
        new_round = RoomRound(
            room_id=room_id, 
            round_number=r, 
            correct_answer=correct_val
        )
        db.add(new_round)
    db.commit()

# --- API Endpoints ---

# تابع کمکی برای دریافت DB Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/rooms/join")
async def join_room(room_id: str, user_id: int, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")

    if not room:
        raise HTTPException(status_code=404, detail="روم یافت نشد")
    
    # بررسی موجودی برای ورود (مثلاً ۱۰ هزار تومان)
    if user.balance < 10000:
        raise HTTPException(status_code=400, detail="موجودی کافی نیست")

    # اگر کاربر قبلاً در این روم بوده، دوباره اضافه نشود
    existing = db.query(RoomParticipant).filter(
        RoomParticipant.room_id == room_id, 
        RoomParticipant.user_id == user_id
    ).first()
    
    if existing:
        return {"message": "شما قبلاً در این روم هستید"}

    # اضافه کردن کاربر به روم
    new_participant = RoomParticipant(room_id=room_id, user_id=user_id)
    db.add(new_participant)
    db.commit()
    
    return {"message": "با موفقیت به روم پیوستید"}

@app.post("/game/submit-answer")
async def submit_answer(answer: int, user_id: int, room_id: str, db: Session = Depends(get_db)):
    # 1. پیدا کردن روم
    room = db.query(Room).filter(Room.id == room_id).first()

    if not room:
        raise HTTPException(
            status_code=404,
            detail="روم یافت نشد"
        )

    # 2. بررسی وضعیت بازی
    if room.status != "playing":
        raise HTTPException(
            status_code=400,
            detail="بازی هنوز شروع نشده یا به پایان رسیده است"
        )
    # ۱. پیدا کردن شرکت‌کننده
    participant = db.query(RoomParticipant).filter(
        RoomParticipant.room_id == room_id, 
        RoomParticipant.user_id == user_id
    ).first()

    if not participant or participant.is_eliminated:
        raise HTTPException(status_code=400, detail="شما در رقابت نیستید")

    # ۲. پیدا کردن راند فعلی کاربر
    current_round_num = participant.current_progress + 1

    # ۳. مراجعه به جدول RoomRound برای پیدا کردن جواب درست
    correct_round_data = db.query(RoomRound).filter(
        RoomRound.room_id == room_id,
        RoomRound.round_number == current_round_num
    ).first()

    if not correct_round_data:
        raise HTTPException(status_code=404, detail="راند یافت نشد")

    # ۴. چک کردن جواب کاربر با جواب ذخیره شده در دیتابیس
    if answer == correct_round_data.correct_answer:
        # کاربر درست گفته!
        participant.current_progress += 1
        
        # بررسی برنده شدن (اگر راند‌های اتاق تمام شده باشد)
        room = db.query(Room).filter(Room.id == room_id).first()
        if participant.current_progress >= room.total_rounds_required: # یا هر تعدادی که راند‌ها هستند
            room.status = "finished"
            await distribute_prize(user_id, room_id, db)
            db.commit()
            return {"status": "winner"}
        
        db.commit()
        return {"status": "success", "next_round": participant.current_progress + 1}
    
    else:
        # کاربر غلط گفته
        return {
        "status": "wrong_answer",
        "current_round": current_round_num,
        "message": "جواب اشتباه است، دوباره تلاش کنید"
        }

# سایر Endpointها مثل ساخت روم و مدیریت تایمر...
