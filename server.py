from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Numeric, DateTime
from sqlalchemy.orm import sessionmaker, Session, relationship,Mapped, mapped_column,DeclarativeBase
from sqlalchemy.ext.declarative import declarative_base
import random
from fastapi import APIRouter, HTTPException, status, Depends, Request
from datetime import datetime, timedelta
from jose import jwt
import uuid
from pydantic import BaseModel
import os
import httpx # برای ارسال درخواست به SMS.ir
# ۱. خواندن آدرس از محیط (Environment Variable)
# اگر در سیستم خودتان هستید و .env ندارید، یک آدرس پیش‌فرض برای تست می‌گذاریم
import os
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from fastapi import Depends
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel, Field,ConfigDict
from passlib.context import CryptContext
import bcrypt
import asyncio


# تعریف پسورد کانتکست (اگر از bcrypt استفاده می‌کنید)
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



# مثال استفاده:
# return ServerResponse(success=True, message="Login successful", data=user_data)

# 1. دریافت URL از محیط Render
DATABASE_URL = os.getenv("DATABASE_URL")

# اگر آدرس با postgres:// شروع شده باشد، آن را به postgresql:// اصلاح می‌کنیم (برای سازگاری با SQLAlchemy 2.0)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    raise ValueError("❌ ERROR: DATABASE_URL is not set in Environment Variables!")

# 2. تنظیمات Engine با قابلیت مدیریت اتصال
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,  # این خط بسیار مهم است: قبل از هر استفاده، سلامت اتصال را چک می‌کند
    pool_size=10,        # تعداد اتصالات همزمان که باز نگه می‌دارد
    max_overflow=20      # اجازه می‌دهد در اوج شلوغی، اتصالات بیشتری ساخته شود
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 3. تابع جادویی Dependency Injection (این بخش کلید اصلی است)
def get_db():
    """
    این تابع باعث می‌شود هر درخواست، یک Session تازه بگیرد 
    و بلافاصله بعد از اتمام کار، آن را ببندد (Close).
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        print(f"❌ Database Error during request: {e}")
        raise e
    finally:
        db.close()  # تضمین می‌کند که کانکشن حتماً بسته می‌شود، حتی اگر خطا رخ دهد



app = FastAPI()

router = APIRouter()
T = TypeVar("T")
class TimerResponse(BaseModel):
    remaining_seconds:int
   
   
    timer_room:int
    room_id:int
class ServerResponse(BaseModel, Generic[T]):
    success: bool
    message: Optional[str] = None
    data: Optional[T] = None
    model_config = ConfigDict(from_attributes=True)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    phone = Column(String, unique=True, index=True)
    balance = Column(Numeric(12, 2), default=0.0)
    password = Column(String)
    full_name = Column(String, nullable=True)
    otpcode = relationship("OTPCode", back_populates="user")

class OTPCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id=Column(Integer, ForeignKey("users.id"))
    code = Column(String)
    expires_at = Column(DateTime)
    is_used = Column(Boolean, default=False)
    user = relationship("User", back_populates="otpcode")
    

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    status = Column(String, default="waiting") 
    total_rounds_required = Column(Integer, default=5)
    total_prize_pool = Column(Numeric(12, 2), default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    game_time = Column(Integer)
    game_start = Column(Integer)
    capacity=Column(Integer)
   
    
    # روابط (Relationships)
    participants = relationship("RoomParticipant", back_populates="room")

class RoomParticipant(Base):
    __tablename__ = "room_participants"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    current_progress = Column(Integer, default=0)  
    Number_of_rounds_won=Column(Integer)  
    status = Column(String)   
    correct_answer = Column(Integer)
    room = relationship("Room")
    user = relationship("User")    
    
    


    

# --- ۲. بخش اسکیماها (Pydantic Schemas) ---
class RoomParticipantSchema(BaseModel):
    user_id: int
    room_id: Optional[int] = None  # یا str بسته به نوع id در جدول Room
    status: Optional[str] = "active"
class TokenResponse(BaseModel): # فقط یک بار و به عنوان BaseModel
    access_token: str
    refresh_token: str
    token_type: str

class UserRegister_phone_Schema(BaseModel):
    phone: str
    
class UserRegister_info_Schema(BaseModel):
    phone:str
    full_name:str
    password:str
class UserLoginSchema(BaseModel):
    phone: str
    password: str
    device_info: Optional[str] = "Unknown Device"

class OTPRequestSchema(BaseModel):
    phone: str

class OTPVerifySchema(BaseModel):
    phone: str
    code: str
    device_info: Optional[str] = "Unknown Device"

class ForgotPasswordRequestSchema(BaseModel):
    phone: str

class ResetPasswordSchema(BaseModel):
    phone: str
    code: str
    new_password: str
class UserResponseSchema(BaseModel):
    id: int
    phone: str
    balance: float
    password: str
    full_name: Optional[str] = None
    

    model_config = ConfigDict(from_attributes=True)
# --- توابع کمکی (Helper Functions) ---
# Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

# فرض می‌کنیم این‌ها از فایل مدل‌ها و تنظیمات شما وارد می‌شوند
# from database import get_db, User, UserSession, pwd_context, SECRET_KEY, ALGORITHM
from sqlalchemy import text

# این بخش را بعد از تعریف engine و قبل از شروع لود شدن روت‌ها قرار دهید:
# @app.on_event("startup")
# def startup_event():
#     try:
#         with engine.begin() as connection:
#             # پاک کردن جدول‌های وابسته و اصلی برای ساخت تمیز از نو
#             connection.execute(text("DROP TABLE IF EXISTS room_participants CASCADE;"))
#             connection.execute(text("DROP TABLE IF EXISTS rooms CASCADE;"))
            
#         # ساخت مجدد تمام جدول‌ها بر اساس مدل‌های پایتون (که id در آن‌ها Integer و autoincrement است)
#         Base.metadata.create_all(bind=engine)
#         print("-> Tables dropped and recreated cleanly with correct schema!")
#     except Exception as e:
#         print(f"-> Error during startup table reset: {e}")
  




# فرض بر این است که مدل‌ها و تنظیمات قبلی ایمپورت شده‌اند
# from database import User, UserSession, OTPCode, db_session, pwd_context, SECRET_KEY, ALGORITHM



# --- تنظیمات SMS.ir (حتماً در Environment Variables قرار دهید) ---
SMS_USERNAME = os.getenv("SMS_USERNAME")
SMS_PASSWORD = os.getenv("SMS_PASSWORD")
SMS_LINE = os.getenv("SMS_LINE")



# --- Routes برای فراموشی رمز ---

@app.post("/auth/forgot-password")
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


# حالت استاندارد در FastAPI
@app.post("/auth/reset-password")
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

    # بررسی وجود کد و منقضی نبودن آن
    if not otp_record or otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="کد تایید اشتباه یا منقضی شده است.")

    # ۳. هش کردن پسورد جدید و آپدیت کاربر
    try:
        # نکته: حتماً باید از pwd_context استفاده کنید تا پسورد به صورت متن ساده ذخیره نشود
        hashed_password = pwd_context.hash(data.new_password)
        user.password = hashed_password
        
        # ۴. پاک کردن کد OTP از دیتابیس برای امنیت بیشتر (استفاده مجدد از آن نشود)
        db.delete(otp_record)
        
        # ۵. غیرفعال کردن تمام نشست‌های قبلی کاربر (Logout از همه دستگاه‌ها)
        # با توجه به مدل UserSession شما
        db.query(UserSession).filter(UserSession.user_id == user.id).update({"is_active": False})
        
        db.commit()
        return {"message": "رمز عبور با موفقیت تغییر یافت. اکنون می‌توانید وارد شوید."}
    
    except Exception as e:
        db.rollback()
        # در محیط توسعه می‌توانید print(e) بگذارید تا خطا را در کنسول ببینید
        raise HTTPException(status_code=500, detail="خطا در تغییر رمز عبور. لطفاً دوباره تلاش کنید.")

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

@app.post("/auth/request-otp")
async def request_otp(data: OTPRequestSchema, db: Session = Depends(get_db)):
    """
    مرحله اول: درخواست کد تایید برای شماره موبایل
    """
      # ۱. تولید کد ۴ یا ۵ رقمی
    otp_code = str(random.randint(1000, 9999))
    user=db.query(User).filter(User.phone==data.phone).first()
    if user:
        raise HTTPException(
            status_code=400, 
            detail="  این شماره موبایل قبلاً ثبت شده است وارد بخش لاگین شوید."
        )
        User.OTPCode(
            code = otp_code,
            expires_at = datetime.utcnow() + timedelta(minutes=2),
        )
    else:
        user=User(
           phone=data.phone,
           balance=0,
        
        
        )
        new_otp = OTPCode(
           phone=data.phone,
           code=otp_code,
           expires_at=datetime.utcnow() + timedelta(minutes=2),
         )
        
   
  
    
    # ۲. ذخیره در دیتابیس (اگر از قبل بود، آپدیت شود)
    
    
   
    db.add(new_otp)
    
    db.commit()

    # ۳. ارسال پیامک
    # sms_sent = await send_sms_otp(data.phone, otp_code)
    
    if not sms_sent:
        # در محیط تست ممکن است SMS کار نکند، اما در محیط واقعی خطا بدهد
        raise HTTPException(status_code=500, detail="خطا در ارسال پیامک. لطفا دوباره تلاش کنید.")

    # return {"message": "کد تایید ارسال شد."}
    return {"message": "شماره تلفن با موفقیت ثبت شد."}

@app.post("/auth/verify-otp")
async def verify_otp(data: OTPVerifySchema, db: Session = Depends(get_db), request: Request = None):
    """
    مرحله دوم: تایید کد و ورود یا ثبت‌نام نهایی
    """
    # ۱. پیدا کردن کد در دیتابیس
    otp_record = db.query(OTPCode).filter(
        OTPCode.phone == data.phone, 
        OTPCode.code == data.code,
        OTPCode.is_used == False # اضافه شد: کد حتما نباید قبلاً استفاده شده باشد
    ).first()

    # ۲. بررسی صحت کد و انقضا
    if not otp_record or otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="کد وارد شده اشتباه یا منقضی شده است.")

    # ۳. بررسی اینکه کاربر وجود دارد یا باید ساخته شود
    user = db.query(User).filter(User.phone == data.phone).first()
    
    # if not user:
    #     # کاربر جدید است -> ثبت‌نام
    #     # تولید یک پسورد رندوم امن برای کاربر جدید
    #     random_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(16))
        
    #     # نکته: حتما باید پسورد را قبل از ذخیره در دیتابیس HASH کنید
    #     # فرض می‌کنیم تابع pwd_context.hash را دارید
    #     # user.password = pwd_context.hash(random_password)
        
    #     # فعلاً برای اینکه کد شما کار کند، فرض می‌کنیم پسورد را مستقیماً می‌دهید (اما هش کردن توصیه می‌شود)
    #     user = User(
    #         phone=data.phone,
    #         password=random_password, 
    #         name=None 
    #     )
    #     db.add(user)
    #     db.commit()
    #     db.refresh(user)
    
    # ۴. پاک کردن کد OTP از دیتابیس برای جلوگیری از استفاده مجدد
    otp_record.is_used = True # بهتر است به جای حذف، فیلد is_used را True کنید
    db.commit()

    # ۵. تولید توکن‌ها (Access & Refresh)
    # این بخش باید بر اساس توابع خودتان باشد
    access_token = create_access_token(data={"sub": data.phone})
    refresh_token = create_refresh_token(data={"sub": data.phone})

    # ۶. ذخیره نشست (Session)
    new_session = UserSession(
        user_id=user.id,
        access_token=access_token,
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
@app.post("/register_by_info", response_model=ServerResponse[UserResponseSchema])
async def register_by_info(user_data: UserRegister_info_Schema, db: Session = Depends(get_db)):
    password_bytes = user_data.password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    
    existing_user = db.query(User).filter(User.phone == user_data.phone).first()
    if not existing_user:
        return ServerResponse(
            message="این شماره موبایل در سیستم ثبت نشده است.", 
            success=False,
        )
    
    existing_user.password=hashed_password
    existing_user.full_name=user_data.full_name
    existing_user.balance=0      # مقدار اولیه موجودی
    
    try:
        
        db.commit()
        db.refresh(existing_user)
        return ServerResponse(message= "ثبت‌ مشخصات با موفقیت انجام شد.",success=True,data=existing_user)
    except Exception as e:
        db.rollback()
        return ServerResponse(message= "خطا در ثبت مشخصات کاربر",success=False)


@app.post("/register_by_phone", response_model=ServerResponse[UserRegister_phone_Schema])
async def register_by_phone(user_data: UserRegister_phone_Schema, db: Session = Depends(get_db)):
    """
    ثبت‌نام کاربر جدید
    """
    # ۱. بررسی اینکه آیا کاربر قبلاً ثبت‌نام کرده یا خیر
    existing_user = db.query(User).filter(User.phone == user_data.phone).first()
    if existing_user:
        return ServerResponse(
            message="این شماره موبایل قبلاً ثبت شده است.", 
            success=False,
        )

    # ۲. هش کردن رمز عبور
    

    # ۳. ایجاد کاربر جدید
    new_user = User(
        phone=user_data.phone,
        
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return ServerResponse(message= "ثبت‌نام با موفقیت انجام شد.",success=True,data=new_user)
    except Exception as e:
        db.rollback()
        return ServerResponse(message= "خطا در ثبت نام کاربر",success=False)

@app.post("/login", response_model=ServerResponse)
async def login(login_data: UserLoginSchema, db: Session = Depends(get_db)):
    """
    ورود کاربر و تولید توکن‌های دسترسی
    """
    # ۱. پیدا کردن کاربر
    user = db.query(User).filter(User.phone == login_data.phone,User.password==login_data.password).first()
    
    # ۲. بررسی وجود کاربر و صحت پسورد
    if not user or not pwd_context.verify(login_data.password, user.password):
        return ServerResponse(
        success=False,
        message="شماره تماس با کلمه عبور اشتباه است!",
        
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
        return ServerResponse(
        success=False,
        message="خطا در ایجاد نشست",
        )

    return ServerResponse(
        success=True,
        message="خوش آمدید!",
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
    )

@app.post("/logout")
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

async def distribute_prizes(winners_data: list, room_id: str, db: Session=Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
     
    """
    توزیع جایزه بین نفرات اول، دوم و سوم.
    winners_data: لیستی از دیکشنری‌ها شامل {'user_id': int, 'rank': int}
    مثال: [{'user_id': 1, 'rank': 1}, {'user_id': 2, 'rank': 2}, {'user_id': 3, 'rank': 3}]
    """
   
    if not room:
        print("Room not found")
        return
     # تبدیل کل مبلغ به Decimal برای دقت محاسباتی
    total_pool = Decimal(str(room.total_prize_pool))

    # تعریف درصدها برای هر رتبه
    # رتبه 1: 60% | رتبه 2: 10% | رتبه 3: 5%
    payout_percentages = {
        1: Decimal('0.60'),
        2: Decimal('0.10'),
        3: Decimal('0.05')
    }
    
    for winner_info in winners_data:
        u_id = winner_info['user_id']
        rank = winner_info['rank']
        
        user = db.query(User).filter(User.id == u_id).first()
        
        if user and rank in payout_percentages:
            # محاسبه مبلغ بر اساس رتبه
            share_percentage = payout_percentages[rank]
            prize_amount = int(total_pool * share_percentage)
            
            # اضافه کردن به موجودی کاربر
            user.balance += prize_amount
            print(f"Rank {rank} (User {u_id}) received: {prize_amount}")
        
        elif user and rank not in payout_percentages:
            print(f"User {u_id} is rank {rank}, but no prize defined for this rank.")

    db.commit()
    print("All prizes distributed successfully.")
def setup_room_rounds( room_id: str, total_rounds: int,db: Session=Depends(get_db)):
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

# Dependency برای گرفتن session در مسیرها
# room_id: Optional[int] = None
@app.post("/join", response_model=ServerResponse)
async def join_room(user_data: RoomParticipantSchema, db: Session = Depends(get_db)):
    # بررسی وجود کاربر
    user = db.query(User).filter(User.id == user_data.user_id).first()
    if not user:
        return ServerResponse(message="کاربر یافت نشد", success=False)
    user_data.user_id=user.id

    # بررسی room_id
    if user_data.room_id is not None and user_data.room_id > 0:
        room = db.query(Room).filter(Room.id == user_data.room_id).first()
        if not room:
            return ServerResponse(message="روم مورد نظر یافت نشد", success=False)
    else:
        # اگر room_id نفرستاده بود، آخرین روم را بگیر
        room = db.query(Room).order_by(Room.id.desc()).first()
        if not room:
            new_room = Room(capacity=0, game_time=current_global_timer)
            db.add(new_room)
            db.commit()
            db.refresh(new_room)
            room = new_room
            
        else:
            room.game_time = current_global_timer
            db.commit()
        

        user_data.room_id = room.id

    # بررسی موجودی (۱۰ هزار تومان)
    if user.balance < 10000:
        return ServerResponse(message="شما مقدار پول کافی برای شرکت در مسابقه را ندارید", success=False)

    # بررسی عضویت قبلی
    existing = db.query(RoomParticipant).filter(
        RoomParticipant.room_id == user_data.room_id,
        RoomParticipant.user_id == user_data.user_id
    ).first()

    if existing:
        # تبدیل به دیکشنری ساده، نه شیء خام دیتابیس
        existing_data = {
            "id": existing.id,
            "room_id": existing.room_id,
            "user_id": existing.user_id
        }
        return ServerResponse(message="شما قبلاً در این روم هستید", success=True, data=existing_data)

    try:
        new_participant = RoomParticipant(room_id=user_data.room_id, user_id=user_data.user_id)
        db.add(new_participant)

        # افزایش شمارنده ظرفیت روم
        room.capacity = (room.capacity or 0) + 1

        db.commit()
        db.refresh(new_participant)

        participant_data = {
            "id": new_participant.id,
            "room_id": new_participant.room_id,
            "user_id": new_participant.user_id
        }
        return ServerResponse(message="با موفقیت به روم پیوستید", success=True, data=participant_data)

    except Exception:
        db.rollback()
        return ServerResponse(message="خطا در پیوستن به روم لطفا اینترنت خود را بررسی کنید", success=False)


        
        
        
      
@app.get("/payment_customer/{user_id}", response_model=ServerResponse)
async def Payment_by_the_customer(user_id:int, db: Session = Depends(get_db)):
    # بررسی وجود کاربر
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ServerResponse(message="کاربر یافت نشد", success=False)    

    try:
        user.balance=10000
        db.commit()
        
        return ServerResponse(message="با موفقیت پول به کیف پولتان واریز شد", success=True,data=user.balance)
        
    except Exception as e:
        db.rollback()
        return ServerResponse(message="خطا", success=False)       

   

import asyncio
from datetime import datetime
ADMIN_TIMER_GAME=120
timer_game=ADMIN_TIMER_GAME
ADMIN_TIMER_ROOM=10
timer_room=ADMIN_TIMER_ROOM
async def master_timer_task():
    while True:
        await asyncio.sleep(1)
        
        db = SessionLocal()
        try:
            # پیدا کردن آخرین اتاق
            room = db.query(Room).order_by(Room.id.desc()).first()

            if not room:
                room = Room(capacity=0, game_time=120, game_start=0)
                db.add(room)
                db.commit()
                db.refresh(room)
                continue

            # فاز ۱: شمارش معکوس ۱۲۰ ثانیه (game_time)
            if room.game_time > 0:
                room.game_time -= 1
                db.commit()
            
            # فاز ۲: وقتی ۱۲۰ ثانیه تمام شد، اگر تایمر ۱۰ ثانیه‌ای هنوز مقداردهی نشده، آن را ۱۰ کن
            elif room.game_start == 0:
                room.game_start = 10
                db.commit()

            # فاز ۳: اگر تایمر ۱۰ ثانیه‌ای در حال کم شدن است
            elif room.game_start > 1:
                room.game_start -= 1
                db.commit()

            # فاز ۴: وقتی ۱۰ ثانیه هم تمام شد، روم جدید ساخته شود
            else:
                new_room = Room(capacity=0, game_time=120, game_start=0)
                db.add(new_room)
                db.commit()

        except Exception as e:
            db.rollback()
            print(f"Timer Error: {e}")
        finally:
            db.close()


        
            
            
    
    
    
    


# این دستور باعث می‌شود وقتی سرور بالا می‌آید، حلقه تایمر هم شروع شود
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(master_timer_task())


@app.get("/timer", response_model=ServerResponse[TimerResponse])
async def get_timer(db: Session = Depends(get_db)):
    # پیدا کردن آخرین اتاق
    room = db.query(Room).order_by(Room.id.desc()).first()
    
    if room:
        # دقت کنید که نام فیلدهای داخل این دیکشنری 
        # باید دقیقاً با فیلدهای کلاس TimerResponse یکی باشد
        da = {
            "remaining_seconds":room.game_time,
            
            "timer_room": room.game_start,
            "room_id": room.id   
        }
        return {"success": True, "data": da}
    
    # بسیار مهم: اگر اتاق پیدا نشد، نباید None برگردانیم
    # باید یک پاسخ استاندارد طبق مدل ServerResponse برگردانیم
    return {"success": False, "data": None} 
    # نکته: اگر TimerResponse اجازه می‌دهد data=None باشد، کد بالا درست است.
    # اگر TimerResponse اجباری است، باید یک شیء خالی از آن بسازید.
        
           
           
        
    

@app.post("/game/submit-answer")
async def submit_answer(answer: int, user_id: int, room_id: str, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="روم یافت نشد")

    # بررسی اتمام زمان (تایمر)
    time_limit = room.total_rounds_required 
    elapsed_time = (datetime.now() - room.start_time).total_seconds() / 60
    
    if elapsed_time >= time_limit:
        # اگر زمان تمام شده ولی هنوز وضعیت finished نشده، بازی را تمام کن
        if room.status != "finished":
            room.status = "finished"
            db.commit()
            await finalize_game_and_payout(room_id, db)
        raise HTTPException(status_code=400, detail="زمان بازی تمام شده است")

    participant = db.query(RoomParticipant).filter(
        RoomParticipant.room_id == room_id, 
        RoomParticipant.user_id == user_id
    ).first()

    # ... (بخش‌های مربوط به چک کردن جواب درست) ...

    if answer == correct_round_data.correct_answer:
        participant.current_progress += 1
        
        # بررسی اینکه آیا این نفر، نفر سوم برنده است؟
        # ما باید تعداد کسانی که راندها را تمام کرده‌اند بشماریم
        winners_count = db.query(RoomParticipant).filter(
            RoomParticipant.room_id == room_id,
            RoomParticipant.current_progress >= room.total_rounds_required
        ).count()

        if winners_count >= 3:
            # اگر تعداد برندگان به ۳ نفر رسید، بازی را تمام کن
            room.status = "finished"
            db.commit()
            await finalize_game_and_payout(room_id, db)
            return {"status": "game_over", "message": "تعداد برندگان تکمیل شد"}

        db.commit()
        return {"status": "success", "next_round": participant.current_progress + 1}
    
    # ... (بقیه کد)


# سایر Endpointها مثل ساخت روم و مدیریت تایمر...
async def finalize_game_and_payout(room_id: str, db: Session= Depends(get_db)):
    # قفل کردن روم برای جلوگیری از اجرای همزمان
    room = db.query(Room).filter(Room.id == room_id).with_for_update().first()

    if not room or room.status == "finished":
        # اگر قبلاً توسط تایمر یا نفر سوم تمام شده بود، دوباره وارد اینجا نشو
        return 

    # تغییر وضعیت به finished برای اینکه هیچ درخواست دیگری وارد نشود
    room.status = "finished"
    db.commit()

    # پیدا کردن برندگان بر اساس امتیاز (از زیاد به کم)
    participants = db.query(RoomParticipant).filter(
        RoomParticipant.room_id == room_id
    ).order_by(RoomParticipant.current_progress.desc()).all()

    winners_data = []
    # فقط نفراتی را بردار که واقعاً راندها را تمام کرده‌اند (حتی اگر کمتر از ۳ نفر باشند)
    for index, p in enumerate(participants[:3]):
        if p.current_progress >= room.total_rounds_required:
            winners_data.append({
                'user_id': p.user_id,
                'rank': index + 1
            })

    # توزیع مبالغ (۶۰٪، ۱۰٪، ۵٪)
    if winners_data:
        await distribute_prizes(winners_data, room_id, db)


    
    # این بخش بسیار حیاتی است:
    # اول سعی می‌کند پورت را از محیط Render بگیرد، اگر نبود از 10000 استفاده می‌کند
