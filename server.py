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

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, Numeric
from sqlalchemy.orm import relationship

# --- مدل‌های دیتابیس اصلاح شده بر اساس منطق بازی شما ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    card_number = Column(String, nullable=True)
    wallet_balance = Column(Numeric(12, 2), default=0) # استفاده از Numeric برای دقت مالی بالا
    is_verified_payment = Column(Boolean, default=False) # ادمین تایید می‌کند که قبلاً پرداخت کرده یا نه
    
    sessions = relationship("UserSession", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    room_participation = relationship("RoomParticipant", back_populates="user")

class Room(Base):
    __tablename__ = "rooms"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String, default="waiting") # waiting, playing, finished
    
    # مدیریت ظرفیت طبق گفته شما (مثلاً 4، 6 یا 10)
    max_capacity = Column(Integer, nullable=False) 
    current_players_count = Column(Integer, default=0)
    
    # اطلاعات بازی
    current_round = Column(Integer, default=1)
    total_rounds = Column(Integer, default=4) # تعداد راندها که ادمین تعیین می‌کند
    
    # ذخیره عدد تصادفی راند (با دقت یک رقم اعشار)
    # مثلا اگر عدد 123.4 باشد، این ستون آن را ذخیره می‌کند
    current_round_target = Column(Numeric(10, 1), nullable=True) 
    
    # ذخیره لیست برندگان یا اطلاعات بازی برای لاگ
    room_logs = Column(Text, nullable=True) 

    participants = relationship("RoomParticipant", back_populates="room")

class RoomParticipant(Base):
    __tablename__ = "room_participants"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    room = relationship("Room", back_populates="participants")
    user = relationship("User", back_populates="room_participation")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Numeric(12, 2), nullable=False)
    type = Column(String, nullable=False) # "deposit", "prize", "entry_fee"
    description = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")

# بقیه مدل‌ها مثل UserSession و OTPCode را طبق کدهای قبلی نگه دار




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
SECRET_KEY = "your_super_secret_key" # حتماً این را در .env قرار بده
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

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

@app.post("/game/join-room")
async def join_room(
    user_id: int, 
    room_id: str, 
    db: Session = GAPGPTMASKTOKENhuimz4ij5soX0X
):
    # شروع یک تراکنش دیتابیسی
    async with db.begin():
        # ۱. پیدا کردن کاربر و قفل کردن ردیف او برای جلوگیری از Race Condition
        # با استفاده از with_for_update، اگر درخواست دوم همزمان برسد، منتظر می‌ماند تا درخواست اول تمام شود
        user = db.query(User).filter(User.id == user_id).with_for_update().first()
        
        if not user:
            raise HTTPException(status_code=404, detail="کاربر یافت نشد")

        # ۲. چک کردن موجودی
        entry_fee = 15000
        if user.wallet_balance < entry_fee:
            raise HTTPException(status_code=400, detail="موجودی کافی نیست")

        # ۳. پیدا کردن روم و قفل کردن آن
        room = db.query(Room).filter(Room.id == room_id).with_for_update().first()
        if not room or room.status != "waiting":
            raise HTTPException(status_code=400, detail="روم در دسترس نیست")

        if room.current_players_count >= room.max_capacity:
            raise HTTPException(status_code=400, detail="روم پر است")

        # ۴. کسر پول و ثبت تراکنش (Audit Log)
        user.wallet_balance -= entry_fee
        
        new_transaction = GAPGPTMASKTOKENhuimz4ij5soX1X
            user_id=user.id,
            amount=-entry_fee,
            type="purchase",
            description=f"ورود به روم {room.id}"
        )
        db.add(new_transaction)

        # ۵. اضافه کردن کاربر به روم
        room.current_players_count += 1
        # (در اینجا منطق اضافه کردن کاربر به لیست بازیکنان روم را هم اضافه کن)
        
        # در پایان بلاک with، تراکنش به صورت خودکار Commit می‌شود
    
    return {"status": "success", "message": "با موفقیت وارد روم شدید"}
@app.post("/game/claim-prize")
async def claim_prize(
    room_id: str, 
    winner_id: int, 
    prize_amount: int, 
    db: Session = GAPGPTMASKTOKENp7hxof6wciaX2X
):
    async with db.begin():
        # ۱. قفل کردن کاربر برنده برای جلوگیری از دریافت جایزه چندباره
        user = db.query(User).filter(User.id == winner_id).with_for_update().first()
        
        # ۲. قفل کردن روم برای اطمینان از اینکه جایزه‌ای قبلاً پرداخت نشده
        room = db.query(Room).filter(Room.id == room_id).with_for_update().first()
        
        if not room or room.status == "finished":
            raise HTTPException(status_code=400, detail="این روم قبلاً تسویه شده است")

        # ۳. اضافه کردن پول به کیف پول
        user.wallet_balance += prize_amount
        
        # ۴. ثبت در تاریخچه تراکنش‌ها
        transaction = GAPGPTMASKTOKENp7hxof6wciaX3X
            user_id=user.id,
            amount=prize_amount,
            type="prize",
            description=f"جایزه روم {room.id}"
        )
        db.add(transaction)

        # ۵. تغییر وضعیت روم به finished برای جلوگیری از پرداخت مجدد
        room.status = "finished"
        
        # در پایان بلاک with، همه تغییرات با هم ذخیره می‌شوند
    
    return {"status": "success", "new_balance": user.wallet_balance}

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

async def verify_code(
    phone: str = Form(...), 
    code: str = Form(...), 
    device_info: str = Form(None),
    ip_address: str = Form(None),
    db: Session = Depends(get_db)
):
    # ۱. بررسی صحت کد OTP (این بخش را با منطق خودت که در دیتابیس ذخیره کردی ترکیب کن)
    is_valid = check_otp_from_db(phone, code) # فرض بر اینکه این تابع را داری
    if not is_valid:
        raise HTTPException(status_code=400, detail="کد وارد شده اشتباه است")

    # ۲. بررسی اینکه آیا کاربر وجود دارد یا خیر
    user = db.query(User).filter(User.phone == phone).first()

    if not user:
        # کاربر جدید است -> تولید توکن موقت برای ثبت‌نام
        registration_token = create_access_token({"sub": phone, "type": "registration"})
        return {
            "status": "new_user",
            "message": "لطفاً برای تکمیل ثبت‌نام، اطلاعات خود را وارد کنید",
            "registration_token": registration_token
        }

    # ۳. کاربر وجود دارد -> ایجاد نشست (Session) و توکن‌ها
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # ایجاد ردیف در جدول UserSession
    new_session = UserSession(
        user_id=user.id,
        refresh_token=refresh_token,
        device_info=device_info,
        ip_address=ip_address
    )
    db.add(new_session)
    db.commit()

    return {
        "status": "success",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@app.post("/auth/refresh")
async def refresh_session(
    refresh_token: str = Form(...), 
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="توکن نامعتبر است")
        
        user_id = payload.get("sub")
        
        # بررسی اینکه آیا این Refresh Token در دیتابیس هنوز فعال است؟
        session = db.query(UserSession).filter(
            UserSession.refresh_token == refresh_token,
            UserSession.is_active == True
        ).first()
        
        if not session:
            raise HTTPException(status_code=401, detail="نشست منقضی یا باطل شده است. دوباره لاگین کنید.")

        # تولید توکن جدید
        new_access_token = create_access_token(data={"sub": str(user_id)})
        
        # بروزرسانی زمان آخرین استفاده
        session.last_used_at = datetime.utcnow()
        db.commit()

        return {
            "access_token": new_access_token,
            "token_type": "bearer"
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="زمان توکن به پایان رسیده است")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="توکن نامعتبر است")


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
