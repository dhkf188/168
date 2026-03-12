"""
认证授权模块 - 使用 werkzeug 替代 passlib
"""

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash, check_password_hash

import server_models as models
from server_database import get_db
from server_config import Config

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码 - 使用 werkzeug"""
    return check_password_hash(hashed_password, plain_password)


def get_password_hash(password: str) -> str:
    """获取密码哈希 - 使用 werkzeug"""
    return generate_password_hash(password)


def authenticate_user(db: Session, username: str, password: str):
    """验证用户"""
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:

    to_encode = data.copy()

    # 🚀 使用 get_utc_now() 获取当前UTC时间（aware）
    from server_timezone import get_utc_now

    if expires_delta:
        # expires_delta 是 timedelta 对象
        expire = get_utc_now() + expires_delta
    else:
        expire = get_utc_now() + timedelta(minutes=Config.ACCESS_TOKEN_EXPIRE_MINUTES)

    # 🚀 JWT的exp字段需要Unix时间戳（秒数，int类型）
    # 将datetime对象转换为Unix时间戳
    expire_timestamp = int(expire.timestamp())

    to_encode.update({"exp": expire_timestamp})

    encoded_jwt = jwt.encode(to_encode, Config.SECRET_KEY, algorithm=Config.ALGORITHM)

    return encoded_jwt


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=[Config.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
):
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="用户已禁用")
    return current_user


async def get_current_admin_user(
    current_user: models.User = Depends(get_current_active_user),
):
    """获取当前管理员用户"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user
