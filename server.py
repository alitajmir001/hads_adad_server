import uuid
import random
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from enum import Enum
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from fastapi import FastAPI, BackgroundTasks, HTTPException

# --- تنظیمات دیتابیس ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./game_server.db"  # برای تست از SQLite استفاده شده
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- مدل‌های دیتابیس ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True)
    wallet_balance = Column(Float, default=0.0)
    card_number = Column(String, nullable=True)
    name = Column(String, nullable=True)

class Room(Base):
    __tablename__ = "rooms"
    id = Column(String, primary_key=True, index=True) # UUID
    status = Column(String, default="waiting") # waiting, playing, finished, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    start_time = Column(DateTime, nullable=True)
    max_capacity = Column(Integer, default=9)
    current_players_count = Column(Integer, default=0)

class Round(Base):
    __tablename__ = "rounds"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))
    round_number = Column(Integer)
    target_number = Column(Float) # عدد تصادفی با یک رقم اعشار

class GameResult(Base):
    __tablename__ = "game_results"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))
    winner_user_id = Column(Integer, ForeignKey("users.id"))
    prize_amount = Column(Float)
    admin_paid = Column(Boolean, default=False)
    payment_date = Column(DateTime, nullable=True)
    player_count_at_end = Column(Integer)

Base.metadata.create_all(bind=engine)

# --- منطق اصلی سرور ---

app = FastAPI()

# مدیریت وضعیت روم‌ها در حافظه برای سرعت بیشتر (در کنار دیتابیس)
active_rooms = {}

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

@app.post("/admin/pay_winner")
def admin_pay(result_id: int, card_number: str):
    """بخش ادمین برای تایید پرداخت"""
    db = SessionLocal()
    result = db.query(GameResult).filter(GameResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    result.admin_paid = True
    result.payment_date = datetime.utcnow()
    db.commit()
    return {"message": "Payment marked as completed"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
