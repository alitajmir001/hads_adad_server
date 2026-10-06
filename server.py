import uuid
import random
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from enum import Enum
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Table, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from fastapi import FastAPI, BackgroundTasks, HTTPException
from passlib.context import CryptContext
from pydantic import BaseModel
import os
import httpx
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import relationship
import uuid
# --- تنظیمات دیتابیس ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./game_server.db"  # برای تست از SQLite استفاده شده
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- مدل‌های دیتابیس ---

 

# تنظیمات هش کردن رمز عبور
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- مدل‌های دیتابیس اصلاح شده ---

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=True)  # برای کاربران ثبت‌نام شده
    
    # اصلاح شده: استفاده از Integer برای جلوگیری از خطای محاسباتی (واحد: تومان)
    wallet_balance = Column(Integer, default=0) 
    
    name = Column(String, nullable=True)
    card_number = Column(String, nullable=True)
    
    # روابط (Relationships)
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user")

class UserSession(Base):
    """مدل جدید برای مدیریت نشست‌ها (مشابه تلگرام)"""
    __tablename__ = "user_sessions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"))
    refresh_token = Column(String, unique=True, index=True, nullable=False)
    
    device_info = Column(String, nullable=True) # مثلا: "iPhone 13 / iOS"
    ip_address = Column(String, nullable=True)
    
    is_active = Column(Boolean, default=True) # برای قابلیت Revoke (ابطال نشست)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sessions")

class Transaction(Base):
    """مدل برای ثبت دقیق تمام تغییرات مالی (Audit Log)"""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Integer, nullable=False) # مثبت برای جایزه، منفی برای خرید
    type = Column(String, nullable=False)   # "deposit", "withdraw", "purchase", "prize"
    description = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")

class Room(Base):
    __tablename__ = "rooms"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String, default="waiting") # waiting, playing, finished, cancelled
    
    max_capacity = Column(Integer, default=9)
    current_players_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    start_time = Column(DateTime, nullable=True)
    
    # ذخیره لیست ID بازیکنان در دیتابیس برای امنیت بیشتر
    player_ids = Column(Text, nullable=True) # ذخیره به صورت رشته JSON یا جداول واسط

class Round(Base):
    __tablename__ = "rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))
    round_number = Column(Integer)
    target_number = Column(Integer) # تغییر به Integer (مثلاً عدد را ضربدر 100 می‌کنیم تا اعشار حفظ شود)

class GameResult(Base):
    __tablename__ = "game_results"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))
    winner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    prize_amount = Column(Integer, default=0)
    admin_paid = Column(Boolean, default=False)
    payment_date = Column(DateTime, nullable=True)





   

class OTPCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, index=True)
    code = Column(String)
    expires_at = Column(DateTime)







# ایجاد جداول در دیتابیس
Base.metadata.create_all(bind=engine)

# --- منطق اصلی سرور ---

app = FastAPI()
@app.on_event("startup")
async def startup_event():
    print("--- ROUTES REGISTERED ---")
    for route in app.routes:
        print(f"Path: {route.path}")


# مدیریت وضعیت روم‌ها در حافظه برای سرعت بیشتر (در کنار دیتابیس)
active_rooms = {}


# این همان کلیدی است که از پنل کپی کردید


# تنظیمات SMS.ir (این‌ها را در فایل .env یا متغیرهای محیطی Render قرار بده)


# ۱. این اطلاعات را در Environment Variables پنل Render ذخیره کن
# (در بخش Settings > Environment در داشبورد Render)
# SMS_USERNAME = os.environ.get("SMS_USERNAME")
# SMS_PASSWORD = os.environ.get("SMS_PASSWORD") # همان Secret Key است
# SMS_LINE = os.environ.get("SMS_LINE")



# این متغیرها رو از محیط سرور می‌خونه (نه داخل کد)
 # مسیردهی‌ها را اصلاح کنید



SECRET_KEY = "secret-your_super_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

def create_tokens(user_id: int, db: Session, device_info: str = None):
    # ۱. تولید Access Token (کوتاه مدت)
    access_expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = jwt.encode(
        {"sub": str(user_id), "exp": access_expire, "type": "access"}, 
        SECRET_KEY, algorithm=ALGORITHM
    )

    # ۲. تولید Refresh Token (بلند مدت و منحصربه‌فرد)
    refresh_token_str = secrets.token_urlsafe(32)
    refresh_expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # ذخیره Refresh Token در توکن (برای اینکه در مرحله Refresh چک شود)
    # اما برای امنیت بالاتر، ما خودِ رشته تصادفی را در دیتابیس ذخیره می‌کنیم
    
    # ۳. ثبت نشست جدید در دیتابیس
    new_session = UserSession(
        user_id=user_id,
        refresh_token=refresh_token_str,
        device_info=device_info,
        is_active=True
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return access_token, refresh_token_str
@app.post("/auth/refresh")
def refresh_access_token(refresh_token: str, db: Session = GAPGPTMASKTOKEN5dnn091tv7dX0X):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
            
        phone = payload.get("sub")
        # اینجا می‌توانید در دیتابیس چک کنید که آیا این Refresh Token باطل شده یا نه (بسیار مهم برای امنیت)
        
        # اگر همه چیز اوکی بود، Access Token جدید بده
        new_access_token, _ = create_tokens(phone)
        return {"access_token": new_access_token}
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh token expired or invalid. Please login again.")


# تابع کمکی برای دریافت Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/check-phone/{phone_number}")
def check_phone(phone_number: str, db: Session = Depends(get_db)):
    # جستجو در دیتابیس برای یافتن شماره مورد نظر
    user = db.query(User).filter(User.phone == phone_number).first()
    
    if user:
        return {"exists": True, "message": "شماره در سیستم موجود است."}
    else:
        return {"exists": False, "message": "شماره یافت نشد."}


async def send_sms_via_provider(phone: str, code: str):
    # این همان آدرسی است که شما فرمودید
    url = "https://api.sms.ir/v1/send/"
    
    # حتما از Environment Variable استفاده کن (توی پنل رندر ست کن)
    api_key = os.environ.get("SMS_API_KEY") 
    line_number = os.environ.get("SMS_LINE")
    
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "text/plain"
    }
    
    payload = {
        "lineNumber": line_number,
        "messageText": f"کد تایید شما در بازی حدس عدد: {code}",
        "mobiles": [phone] # SMS.ir معمولا لیست موبایل‌ها رو به صورت آرایه میخواد
    }

    try:
        async with httpx.AsyncClient() as client:
            # استفاده از متد POST (بسیار مهم!)
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            
            data = response.json()
            
            # بررسی پاسخ
            if response.status_code == 200 and data.get("status") == 1:
                print(f"پیامک با موفقیت به {phone} ارسال شد.")
                return True
            else:
                # این پرینت توی لاگ رندر میفته و بهت میگه دقیقا چه خطایی داده
                print(f"خطا در ارسال: {data.get('message')} - کد خطا: {data.get('status')}")
                return False
                
    except Exception as e:
        print(f"خطای شبکه: {e}")
        return False

@app.get("/auth/sessions")
def get_my_sessions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # نمایش تمام نشست‌های فعال کاربر
    sessions = db.query(UserSession).filter(UserSession.user_id == current_user.id).all()
    return sessions

@app.post("/auth/sessions/terminate/{session_id}")
def terminate_session(session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # پیدا کردن نشست مورد نظر
    session = db.query(UserSession).filter(
        UserSession.id == session_id, 
        UserSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # باطل کردن نشست (مثل تلگرام)
    session.is_active = False
    db.commit()
    
    return {"message": "Session terminated successfully. If this was a hacker, they are now kicked out!"}



def calculate_prize(player_count: int) -> float:
    """محاسبه جایزه بر اساس تعداد بازیکنان"""
    if player_count >= 3:
        return 30000.0
    elif player_count >= 2:
        return 20000.0
    else:
        return 10000.0 # حالت پیش‌فرض برای تک‌نفره یا موارد دیگر

async def room_timer_task(room_id: str, user_ids: List[int]):
    """وظیفه پس‌زمینه برای مدیریت زمان ۵ دقیقه"""
    await asyncio.sleep(300) # ۵ دقیقه انتظار
    
    db = SessionLocal()
    room = db.query(Room).filter(Room.id == room_id).first()
    
    if room and room.status == "waiting":
        # اگر در ۵ دقیقه کسی نیامده بود یا روم تکمیل نشده بود
        print(f"Room {room_id} expired. Refunding users...")
        for u_id in user_ids:
            user = db.query(User).filter(User.id == u_id).first()
            if user:
                user.wallet_balance += 15000.0 # برگشت ورودی ۱۵ هزار تومان
        
        room.status = "cancelled"
        db.commit()
    db.close()

@app.post("/join_room/{user_phone}")
async def join_room(user_phone: str, background_tasks: BackgroundTasks):
    db = SessionLocal()
    user = db.query(User).filter(User.phone == user_phone).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.wallet_balance < 15000:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # پیدا کردن یک روم خالی یا ساخت روم جدید
    room = db.query(Room).filter(Room.status == "waiting").first()
    
    if not room:
        room = Room(id=str(uuid.uuid4()), status="waiting")
        db.add(room)
        db.commit()
        # شروع تایمر ۵ دقیقه‌ای برای روم جدید
        background_tasks.add_task(room_timer_task, room.id, [])
    
    if room.current_players_count < room.max_capacity:
        # کسر مبلغ ورودی
        user.wallet_balance -= 15000
        room.current_players_count += 1
        
        # اگر اولین نفر وارد شد، زمان شروع را ثبت کن
        if room.current_players_count == 1:
            room.start_time = datetime.utcnow()
            # اگر اولین نفر بود، تایمر را مدیریت کن (در اینجا لیست بازیکنان را نگه می‌داریم)
            # نکته: در سیستم واقعی باید لیست IDها را در دیتابیس ذخیره کنید
            
        db.commit()
        
        # اگر روم پر شد، شروع بازی
        if room.current_players_count == 9:
            room.status = "playing"
            # ایجاد ۵ راند
            for i in range(1, 6):
                new_round = Round(
                    room_id=room.id, 
                    round_number=i, 
                    target_number=round(random.uniform(0, 100), 1)
                )
                db.add(new_round)
            db.commit()
            
        return {"message": "Joined successfully", "room_id": room.id}
    
    return {"message": "Room full, please wait for next one."}
router = APIRouter()

@router.post("/auth/register")
def register_user(
    data: RegistrationInput, # شامل phone و اطلاعات دیگر
    current_temp_user: access_token, # توکن موقتی که در مرحله verify-code گرفتی
    db: Session = Depends(get_db)):,
    device_info: str = "Unknown Device"
):
    # ۱. ابتدا توکن موقت را چک کن تا مطمئن شویم کاربر مرحله OTP را رد کرده است
    # (این مرحله امنیت را تضمین می‌کند که کسی نتواند مستقیم ثبت‌نام کند)
    try:
        payload = jwt.decode(current_temp_user, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "registration":
            raise HTTPException(status_code=401, detail="Invalid token type")
        phone_from_token = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Registration token expired or invalid")

    # ۲. چک کردن اینکه آیا کاربر قبلاً ثبت‌نام کرده یا نه
    existing_user = db.query(User).filter(User.phone == phone_from_token).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    # ۳. ساخت کاربر جدید در دیتابیس
    new_user = User(
        phone = phone_from_token,
        username = data.username,
        # سایر فیلدها...
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # ۴. مرحله طلایی: تولید توکن‌های اصلی و ثبت نشست (Session)
    # اینجا همان جایی است که کاربر رسماً وارد بازی می‌شود و "ردپا" در دیتابیس می‌ماند
    access_token, refresh_token = create_tokens(
        user_id=new_user.id, 
        db=db, 
        device_info=device_info
    )

    return {
        "message": "Registration successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "is_new_user": False
    }
@app.get("/room_status/{room_id}")
def get_room_status(room_id: str):
    db = SessionLocal()
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        return {"error": "Room not found"}
    
    rounds = db.query(Round).filter(Round.room_id == room_id).all()
    round_data = [{"round": r.round_number, "target": r.target_number} for r in rounds]
    
    return {
        "status": room.status,
        "players": room.current_players_count,
        "rounds": round_data
    }


def process_purchase(db: Session, user_id: int, amount: int):
    try:
        # ۱. شروع یک تراکنش (Transaction)
        # استفاده از with_for_update باعث می‌شود این ردیف در دیتابیس قفل شود
        user = db.query(User).filter(User.id == user_id).with_for_update().first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # ۲. چک کردن موجودی (حالا کاملاً امن است چون ردیف قفل شده)
        if user.wallet_balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")

        # ۳. کسر مبلغ
        user.wallet_balance -= amount
        
        # ۴. ثبت تاریخچه تراکنش (حتماً برای Audit Log لازم است)
        new_transaction = Transaction(
            user_id=user.id,
            amount=-amount,
            type="purchase",
            description="Buying game item"
        )
        db.add(new_transaction)

        # ۵. تایید نهایی (Commit) - در این لحظه قفل باز می‌شود
        db.commit()
        return {"message": "Purchase successful", "new_balance": user.wallet_balance}

    except Exception as e:
        # اگر هر مشکلی پیش بیاید، همه چیز به حالت اول برمی‌گردد
        db.rollback()
        raise e


SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

@app.post("/admin/pay_winner/{result_id}")
def admin_pay(result_id: int):
    """بخش ادمین برای تایید پرداخت"""
    db = SessionLocal()
    result = db.query(GameResult).filter(GameResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    result.admin_paid = True
    result.payment_date = datetime.utcnow()
    db.commit()
    return {"message": "Payment marked as completed"}



# مدل‌های ورودی برای درخواست‌ها
class PhoneInput(BaseModel):
    phone: str

class VerifyCodeInput(BaseModel):
    phone: str
    code: str

class SetPasswordInput(BaseModel):
    phone: str
    password: str
    token: str # توکن موقتی که در مرحله قبل گرفتیم
OTP_VALIDITY_SECONDS = 120
@app.post("/auth/request-code")
async def request_code(data: PhoneInput, background_tasks: BackgroundTasks):
    db = SessionLocal()
    
    # ۱. تولید کد ۴ رقمی
    code = str(random.randint(1000, 9999))
    expires = datetime.utcnow() + timedelta(seconds=OTP_VALIDITY_SECONDS)
    db.query(OTPCode).filter(
    OTPCode.phone == data.phone
    ).delete()

    db.commit()
    # ۲. ذخیره در دیتابیس
    new_otp = OTPCode(phone=data.phone, code=code, expires_at=expires)
    db.add(new_otp)
    db.commit()
    db.close()
    
    # ۳. فراخوانی تابع واقعی ارسال پیامک (اینجا تغییر اصلی است)
    # از background_tasks استفاده می‌کنیم تا کاربر منتظر ارسال پیامک نماند و سرعت بالا برود
    background_tasks.add_task(send_sms_via_provider, data.phone, code)
    
    return {
        "message": "Code sent successfully",
        "expires_in": OTP_VALIDITY_SECONDS 
    }



def quick_deduct(db: Session, user_id: int, amount: int):
    # این دستور در سطح دیتابیس انجام می‌شود: 
    # UPDATE users SET wallet_balance = wallet_balance - amount WHERE id = user_id AND wallet_balance >= amount
    result = db.execute(
        update(User)
        .where(User.id == user_id)
        .where(User.wallet_balance >= amount)
        .values(wallet_balance=User.wallet_balance - amount)
    )
    db.commit()

    if result.rowcount == 0:
        # اگر ردیف آپدیت نشد، یعنی یا کاربر نبود یا موجودی کافی نبود
        raise HTTPException(status_code=400, detail="Transaction failed: Insufficient funds or invalid user")
    
    return {"message": "Success"}

@app.post("/auth/verify-code")
async def verify_code(data: VerifyCodeInput, device_info: str = "Unknown Device", db: Session = GAPGPTMASKTOKENh4rp0fr0kybX0X
    # ۱. چک کردن اعتبار OTP در دیتابیس
    otp_record = db.query(OTPCode).filter(
        OTPCode.phone == data.phone, 
        OTPCode.code == data.code,
        OTPCode.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    
    # ۲. حذف کد استفاده شده برای جلوگیری از Replay Attack
    db.delete(otp_record)
    db.commit()

    # ۳. پیدا کردن کاربر
    user = db.query(User).filter(User.phone == data.phone).first()

    if user:
        # --- سناریوی اول: کاربر قدیمی است (Login) ---
        # تولید توکن‌های جفت (Access + Refresh) و ثبت نشست در دیتابیس
        GAPGPTMASKTOKENh4rp0fr0kybX1X, GAPGPTMASKTOKENh4rp0fr0kybX2X = GAPGPTMASKTOKENh4rp0fr0kybX3X, db, device_info)
        
        return {
            "message": "Login successful",
            "GAPGPTMASKTOKENh4rp0fr0kybX4X": GAPGPTMASKTOKENh4rp0fr0kybX5X,
            "GAPGPTMASKTOKENh4rp0fr0kybX6X": GAPGPTMASKTOKENh4rp0fr0kybX7X,
            "is_new_user": False
        }
    else:
        # --- سناریوی دوم: کاربر جدید است (Registration) ---
        # در اینجا ما هنوز کاربر را در جدول User نمی‌سازیم، 
        # بلکه یک توکن موقت (Temporary Token) می‌دهیم تا مرحله بعدی (تعیین نام/رمز) را طی کند.
        
        temp_token_expire = datetime.utcnow() + timedelta(minutes=5)
        GAPGPTMASKTOKENh4rp0fr0kybX8X = GAPGPTMASKTOKENh4rp0fr0kybX9X"sub": data.phone, "type": "registration", "exp": temp_token_expire}, 
        SECRET_KEY, algorithm=ALGORITHM)
        
        return {
            "message": "Code verified. Please complete your registration.",
            "GAPGPTMASKTOKENh4rp0fr0kybX10X": GAPGPTMASKTOKENh4rp0fr0kybX11X,
            "is_new_user": True
        }


# @app.post("/auth/set-password")
# async def set_password(data: SetPasswordInput):
#     db = SessionLocal()
    
#     # ۱. چک کردن توکن موقت
#     try:
#         payload = jwt.decode(data.token, SECRET_KEY, algorithms=[ALGORITHM])
#         if payload.get("type") != "registration":
#             raise HTTPException(status_code=400, detail="Invalid token type")
#         phone_in_token = payload.get("sub")
#     except:
#         raise HTTPException(status_code=401, detail="Invalid or expired registration token")

#     if phone_in_token != data.phone:
#         raise HTTPException(status_code=400, detail="Phone number mismatch")

#     # ۲. ساخت کاربر
#     user = db.query(User).filter(User.phone == data.phone).first()
#     if user:
#         raise HTTPException(status_code=400, detail="User already exists")
    
#     hashed_pw = get_password_hash(data.password)
#     new_user = User(phone=data.phone, password=hashed_pw)
#     db.add(new_user)
#     db.commit()
    
#     # ۳. بازگشت توکن نهایی
#     access_token = create_access_token({"sub": data.phone, "type": "access"})
#     return {"message": "Account created successfully", "access_token": access_token}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
