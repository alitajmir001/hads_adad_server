import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Numeric, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
import random

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

def get_target_for_round(round_number: int) -> int:
    """
    این تابع تعیین می‌کند در هر راند، عدد درست چه باشد.
    برای اینکه همه در یک راند هدف مشترک داشته باشند، از یک فرمول یا Seed استفاده می‌کنیم.
    """
    random.seed(round_number) # ثابت نگه داشتن عدد برای همه در یک راند مشخص
    return random.randint(1, 100)

async def distribute_prize(winner_id: int, room_id: str, db: Session):
    """
    پرداخت جایزه به برنده و کسر از استخر جایزه.
    این تابع باید بسیار امن باشد.
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    winner = db.query(User).filter(User.id == winner_id).first()
    
    if room and winner:
        prize_amount = room.total_prize_pool * 0.6  # ۶۰ درصد برای برنده
        winner.balance += prize_amount
        # ۴۰ درصد باقی‌مانده به عنوان کارمزد سیستم در دیتابیس باقی می‌ماند
        print(f"Winner {winner_id} received {prize_amount}")
# فرض کن این تابع هنگام ساخت اتاق اجرا می‌شود
def setup_room_rounds(db: Session, room_id: str, total_rounds: int):
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
async def submit_answer(answer: int, user_id: int, room_id: str, db: Session = Depends(get_db)
    # ۱. پیدا کردن شرکت‌کننده
    participant = db.query(RoomParticipant).filter(
        RoomParticipant.room_id == room_id, 
        RoomParticipant.user_id == user_id
    ).with_for_update().first()

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
