# server_site_routes.py - 修复上传部分

import os
import uuid
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_
from pydantic import BaseModel
from server_auth import PermissionChecker
from server_permissions import PermissionCode

from server_database import get_db
from server_auth import get_current_active_user, PermissionChecker
import server_models as models
from server_site_models import Site, SiteEmployeeAccount, SiteDataRecord, UploadBatch
from server_timezone import (
    get_beijing_now,
    parse_beijing_datetime,
    make_naive,
    to_utc_time,
    BEIJING_TZ,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/site-stats", tags=["站点数据"])


# ==================== 辅助函数 ====================


def format_seconds_to_time(seconds: int) -> str:
    """将秒数格式化为时间字符串"""
    if seconds <= 0:
        return "0秒"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes > 0 and secs > 0:
        return f"{minutes}分{secs}秒"
    elif minutes > 0:
        return f"{minutes}分"
    else:
        return f"{secs}秒"


def parse_datetime_flexible(datetime_str):
    """灵活解析日期时间字符串"""
    if not datetime_str or pd.isna(datetime_str):
        return None

    datetime_str = str(datetime_str).strip()
    if datetime_str == "nan" or datetime_str == "" or datetime_str == "None":
        return None

    # 常见的时间格式
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y%m%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(datetime_str, fmt)
        except:
            continue

    # 如果都失败，尝试用pandas解析
    try:
        return pd.to_datetime(datetime_str)
    except:
        pass

    return None


def calculate_process_seconds(start_time_str, end_time_str) -> int:
    """计算处理时间（秒）"""
    start_time = parse_datetime_flexible(start_time_str)
    end_time = parse_datetime_flexible(end_time_str)

    if start_time and end_time and end_time > start_time:
        return int((end_time - start_time).total_seconds())
    return 0


def safe_get_cell(row, index, default=None):
    """安全获取单元格值，处理越界和NaN"""
    try:
        if index >= len(row):
            return default
        val = row[index]
        if pd.isna(val):
            return default
        return val
    except:
        return default


# ==================== Pydantic Schema ====================


class SiteCreate(BaseModel):
    code: str
    name: str
    sort_order: int = 0


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class EmployeeAccountCreate(BaseModel):
    site_id: int
    name: str
    account_name: str
    shift: str = "day"


class EmployeeAccountUpdate(BaseModel):
    name: Optional[str] = None
    account_name: Optional[str] = None
    shift: Optional[str] = None
    is_active: Optional[bool] = None


# ==================== 站点管理 API ====================


@router.get("/sites")
def get_sites(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        PermissionChecker(PermissionCode.SITE_VIEW.value)
    ),
):
    """获取站点列表"""
    query = db.query(Site)
    if is_active is not None:
        query = query.filter(Site.is_active == is_active)

    sites = query.order_by(Site.sort_order, Site.code).all()

    result = []
    for site in sites:
        site_dict = site.to_dict()
        data_count = (
            db.query(SiteDataRecord).filter(SiteDataRecord.site_id == site.id).count()
        )
        account_count = (
            db.query(SiteEmployeeAccount)
            .filter(SiteEmployeeAccount.site_id == site.id)
            .count()
        )
        site_dict["data_count"] = data_count
        site_dict["account_count"] = account_count
        result.append(site_dict)

    return {"items": result, "total": len(result)}


@router.post("/sites")
def create_site(
    data: SiteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        PermissionChecker(PermissionCode.SITE_EDIT.value)
    ),
):
    """创建站点"""
    existing = db.query(Site).filter(Site.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="站点代码已存在")

    site = Site(
        code=data.code,
        name=data.name,
        sort_order=data.sort_order,
    )
    db.add(site)
    db.commit()
    db.refresh(site)

    logger.info(f"站点创建: {data.code} by {current_user.username}")
    return site.to_dict()


@router.put("/sites/{site_id}")
def update_site(
    site_id: int,
    data: SiteUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """更新站点"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="站点不存在")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(site, key, value)

    db.commit()
    db.refresh(site)

    logger.info(f"站点更新: {site.code} by {current_user.username}")
    return site.to_dict()


@router.delete("/sites/{site_id}")
def delete_site(
    site_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """删除站点"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="站点不存在")

    data_count = (
        db.query(SiteDataRecord).filter(SiteDataRecord.site_id == site_id).count()
    )
    if data_count > 0:
        raise HTTPException(
            status_code=400, detail=f"该站点有 {data_count} 条数据记录，请先删除数据"
        )

    db.delete(site)
    db.commit()

    logger.info(f"站点删除: {site.code} by {current_user.username}")
    return {"message": "站点已删除"}


# ==================== 员工账号管理 API ====================


@router.get("/employee-accounts")
def get_employee_accounts(
    site_id: Optional[int] = None,
    account_name: Optional[str] = None,
    shift: Optional[str] = None,
    skip: int = 0,  # ✅ 添加分页参数
    limit: int = 20,  # ✅ 添加分页参数
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取站点员工账号列表（支持分页）"""
    query = db.query(SiteEmployeeAccount)

    if site_id:
        query = query.filter(SiteEmployeeAccount.site_id == site_id)
    if account_name:
        query = query.filter(
            SiteEmployeeAccount.account_name.ilike(f"%{account_name}%")
        )
    if shift:
        query = query.filter(SiteEmployeeAccount.shift == shift)

    # ✅ 获取总数
    total = query.count()

    # ✅ 分页查询
    accounts = (
        query.order_by(SiteEmployeeAccount.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = []
    for acc in accounts:
        item = acc.to_dict()
        data_count = (
            db.query(SiteDataRecord)
            .filter(SiteDataRecord.employee_account_id == acc.id)
            .count()
        )
        item["data_count"] = data_count
        items.append(item)

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(items)) < total,
    }


@router.post("/employee-accounts")
def create_employee_account(
    data: EmployeeAccountCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """创建站点员工账号"""
    site = db.query(Site).filter(Site.id == data.site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="站点不存在")

    existing = (
        db.query(SiteEmployeeAccount)
        .filter(
            SiteEmployeeAccount.site_id == data.site_id,
            SiteEmployeeAccount.account_name == data.account_name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"站点 {site.code} 下账号 {data.account_name} 已存在",
        )

    account = SiteEmployeeAccount(
        site_id=data.site_id,
        name=data.name,
        account_name=data.account_name,
        shift=data.shift,  # ===== 新增 =====
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    logger.info(
        f"员工账号创建: {data.account_name} -> 站点 {site.code} (班次:{data.shift}) by {current_user.username}"
    )
    return account.to_dict()


@router.put("/employee-accounts/{account_id}")
def update_employee_account(
    account_id: int,
    data: EmployeeAccountUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """更新站点员工账号"""
    account = (
        db.query(SiteEmployeeAccount)
        .filter(SiteEmployeeAccount.id == account_id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(account, key, value)

    db.commit()
    db.refresh(account)

    logger.info(f"员工账号更新: {account.account_name} by {current_user.username}")
    return account.to_dict()


@router.delete("/employee-accounts/{account_id}")
def delete_employee_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """删除站点员工账号"""
    account = (
        db.query(SiteEmployeeAccount)
        .filter(SiteEmployeeAccount.id == account_id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    data_count = (
        db.query(SiteDataRecord)
        .filter(SiteDataRecord.employee_account_id == account_id)
        .count()
    )
    if data_count > 0:
        raise HTTPException(
            status_code=400, detail=f"该账号有 {data_count} 条数据记录，请先删除数据"
        )

    db.delete(account)
    db.commit()

    logger.info(f"员工账号删除: {account.account_name} by {current_user.username}")
    return {"message": "账号已删除"}


# ==================== 数据上传 API ====================


@router.post("/upload")
async def upload_site_data(
    file: UploadFile = File(...),
    site_id: int = Form(...),
    shift: str = Form(...),
    date: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        PermissionChecker(PermissionCode.SITE_EDIT.value)
    ),
):
    """
    上传站点数据文件
    支持 Excel (.xlsx, .xls) 和 CSV 格式
    列要求：
        R列：开始时间（第18列，索引17）
        S列：完成时间（第19列，索引18）
        V列：后台账号（第22列，索引21）
    """
    # 验证站点存在
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="站点不存在")

    # 验证班次
    if shift not in ["day", "night"]:
        raise HTTPException(status_code=400, detail="班次必须是 day 或 night")

    # 生成批次ID
    batch_id = (
        f"{site.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )

    # 创建上传批次记录
    batch = UploadBatch(
        batch_id=batch_id,
        site_id=site_id,
        filename=file.filename,
        file_type=file.filename.split(".")[-1] if "." in file.filename else "unknown",
        status="processing",
        uploaded_by=current_user.id,
    )
    db.add(batch)
    db.commit()

    # 保存临时文件
    import tempfile

    file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else "csv"
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}")

    try:
        content = await file.read()
        temp_file.write(content)
        temp_file.close()

        # 解析文件 - 使用更健壮的方式
        df = None

        if file_ext in ["xlsx", "xls"]:
            # Excel文件 - 使用openpyxl或xlrd
            try:
                if file_ext == "xlsx":
                    df = pd.read_excel(temp_file.name, engine="openpyxl", header=None)
                else:
                    df = pd.read_excel(temp_file.name, engine="xlrd", header=None)
            except Exception as e:
                logger.error(f"读取Excel文件失败: {e}")
                raise HTTPException(
                    status_code=400, detail=f"读取Excel文件失败: {str(e)}"
                )

        elif file_ext == "csv":
            # CSV文件 - 使用更健壮的解析方式，处理不规则行
            try:
                # 先尝试用默认方式读取
                try:
                    df = pd.read_csv(
                        temp_file.name,
                        encoding="utf-8",
                        header=None,
                        on_bad_lines="skip",  # 跳过错误行
                        engine="python",  # 使用python引擎更灵活
                    )
                except:
                    # 尝试其他编码
                    try:
                        df = pd.read_csv(
                            temp_file.name,
                            encoding="gbk",
                            header=None,
                            on_bad_lines="skip",
                            engine="python",
                        )
                    except:
                        # 最后尝试用python手动解析
                        df = parse_csv_robust(temp_file.name)

                if df is None or len(df) == 0:
                    raise HTTPException(status_code=400, detail="CSV文件为空或无法解析")

            except Exception as e:
                logger.error(f"读取CSV文件失败: {e}")
                raise HTTPException(
                    status_code=400, detail=f"读取CSV文件失败: {str(e)}"
                )

        else:
            raise HTTPException(status_code=400, detail=f"不支持的文件格式: {file_ext}")

        logger.info(f"文件解析成功，共 {len(df)} 行，{len(df.columns)} 列")

        # ✅ 修改：传递 date 参数
        stats_data, matched_count, unmatched_count = await parse_site_data_advanced(
            df, site, batch_id, shift, current_user.id, db, date  # 添加 date 参数
        )

        # 更新批次状态
        batch.record_count = stats_data["total_records"]
        batch.matched_count = matched_count
        batch.unmatched_count = unmatched_count
        batch.status = "completed"
        db.commit()

        logger.info(
            f"站点数据上传完成: {batch_id}, 记录数={stats_data['total_records']}, 匹配={matched_count}, 未匹配={unmatched_count}"
        )

        return {
            "success": True,
            "batch_id": batch_id,
            "site_code": site.code,
            "stats": stats_data,
            "matched_count": matched_count,
            "unmatched_count": unmatched_count,
            "skipped_by_shift": stats_data.get("skipped_by_shift", 0),
            "message": f"上传完成，共处理 {stats_data['total_records']} 条记录，匹配 {matched_count} 个账号",
        }

    except HTTPException:
        raise
    except Exception as e:
        batch.status = "failed"
        batch.error_message = str(e)
        db.commit()
        logger.error(f"站点数据上传失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"解析文件失败: {str(e)}")
    finally:
        if os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except:
                pass


def parse_csv_robust(filepath):
    """健壮的CSV解析，处理不规则的行"""
    import csv

    rows = []
    max_columns = 0

    # 尝试不同编码
    for encoding in ["utf-8", "gbk", "gb2312", "latin-1"]:
        try:
            with open(filepath, "r", encoding=encoding) as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:  # 跳过空行
                        rows.append(row)
                        max_columns = max(max_columns, len(row))
            if rows:
                logger.info(
                    f"CSV解析成功，编码: {encoding}, 行数: {len(rows)}, 最大列数: {max_columns}"
                )
                break
        except:
            continue

    if not rows:
        return None

    # 统一列数（不足的补空，过多的截断）
    for i in range(len(rows)):
        if len(rows[i]) < max_columns:
            rows[i].extend([""] * (max_columns - len(rows[i])))
        elif len(rows[i]) > max_columns:
            rows[i] = rows[i][:max_columns]

    # 转换为DataFrame
    import pandas as pd

    return pd.DataFrame(rows)


async def parse_site_data_advanced(
    df: pd.DataFrame,
    site: Site,
    batch_id: str,
    shift: str,
    user_id: int,
    db: Session,
    upload_date: Optional[str] = None,  # ✅ 添加这个参数
):
    """
    解析站点数据文件 - 按账号统计笔数和平均处理时间
    只保存与上传班次匹配的员工数据
    支持去重：同一站点+同一账号+同一天+同班次的数据会更新而非重复插入
    """
    from sqlalchemy import func, and_
    from server_timezone import get_beijing_now, to_utc_time, make_naive, BEIJING_TZ
    from datetime import datetime, timedelta

    # ===== 获取该站点的员工账号映射，同时获取班次信息 =====
    accounts = (
        db.query(SiteEmployeeAccount)
        .filter(
            SiteEmployeeAccount.site_id == site.id,
            SiteEmployeeAccount.is_active == True,
        )
        .all()
    )

    # 账号到员工ID的映射
    account_to_employee = {acc.account_name: acc.id for acc in accounts}
    # 账号到员工姓名的映射
    employee_names = {acc.account_name: acc.name for acc in accounts}
    # 账号到班次的映射
    account_to_shift = {acc.account_name: acc.shift for acc in accounts}

    # 定义列索引
    START_TIME_COL = 17  # R列
    END_TIME_COL = 18  # S列
    ACCOUNT_COL = 21  # V列

    total_rows = len(df)
    logger.info(f"开始解析文件，总行数: {total_rows}")
    logger.info(f"上传班次: {shift}")
    logger.info(f"上传日期: {upload_date}")  # ✅ 添加日志

    # 统计每个账号的数据
    account_stats = {}
    total_records = 0
    error_rows = 0
    skipped_rows = 0
    skipped_by_shift = 0
    skipped_unconfigured = 0

    for idx in range(total_rows):
        try:
            row = df.iloc[idx]

            if len(row) <= ACCOUNT_COL:
                skipped_rows += 1
                continue

            account_val = safe_get_cell(row, ACCOUNT_COL)
            if not account_val:
                continue

            account_name = str(account_val).strip()
            if not account_name or account_name == "nan" or account_name == "":
                continue

            # ===== 🔧 修复：只处理已配置的员工，未配置的员工不统计 =====
            if account_name not in account_to_employee:
                skipped_unconfigured += 1
                logger.debug(f"跳过未配置账号: {account_name}")
                continue

            # 检查班次是否匹配
            employee_shift = account_to_shift.get(account_name)
            if employee_shift != shift:
                skipped_by_shift += 1
                logger.debug(
                    f"跳过账号 {account_name}: 班次不匹配 (员工班次:{employee_shift}, 上传班次:{shift})"
                )
                continue

            # 初始化账号统计
            if account_name not in account_stats:
                account_stats[account_name] = {
                    "account_name": account_name,
                    "total_orders": 0,
                    "total_time_seconds": 0,
                    "valid_time_count": 0,
                    "employee_shift": employee_shift,
                    "employee_account_id": account_to_employee[account_name],
                }

            start_time_str = safe_get_cell(row, START_TIME_COL)
            end_time_str = safe_get_cell(row, END_TIME_COL)

            process_seconds = 0
            if start_time_str and end_time_str:
                process_seconds = calculate_process_seconds(
                    str(start_time_str), str(end_time_str)
                )

            account_stats[account_name]["total_orders"] += 1
            if process_seconds > 0:
                account_stats[account_name]["total_time_seconds"] += process_seconds
                account_stats[account_name]["valid_time_count"] += 1
            total_records += 1

        except Exception as e:
            error_rows += 1
            logger.warning(f"解析第 {idx} 行失败: {e}")
            continue

    logger.info(
        f"解析完成: 总记录数={total_records}, 账号数={len(account_stats)}, "
        f"跳过行={skipped_rows}, 错误行={error_rows}, "
        f"未配置跳过={skipped_unconfigured}, 班次不匹配跳过={skipped_by_shift}"
    )

    if total_records == 0:
        raise HTTPException(
            status_code=400,
            detail="文件中没有找到有效的数据行，请检查：\n"
            "1. 账号是否已在员工管理中配置\n"
            "2. 账号的班次是否与上传班次匹配",
        )

    # ===== ✅ 关键修改：使用用户选择的日期 =====
    if upload_date:
        # 使用用户选择的日期
        try:
            stat_date = datetime.strptime(upload_date, "%Y-%m-%d")
            stat_date = stat_date.replace(tzinfo=BEIJING_TZ)
            logger.info(f"使用用户选择的日期: {upload_date}")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"日期格式错误: {upload_date}")
    else:
        # 如果没有传递日期，使用当前时间
        stat_date = get_beijing_now()
        logger.warning(
            f"未传递日期参数，使用当前时间: {stat_date.strftime('%Y-%m-%d')}"
        )

    # 转换为UTC naive时间用于数据库查询和存储
    stat_date_start_utc = make_naive(to_utc_time(stat_date))
    logger.info(f"统计日期(UTC): {stat_date_start_utc}")

    # ===== 使用精确的日期匹配 =====
    existing_records = {}
    existing_query = (
        db.query(SiteDataRecord)
        .filter(
            SiteDataRecord.site_id == site.id,
            SiteDataRecord.shift == shift,
            SiteDataRecord.date == stat_date_start_utc,
        )
        .all()
    )

    for record in existing_query:
        key = record.account_name
        existing_records[key] = record

    logger.info(f"当天已存在 {len(existing_records)} 条记录，将进行去重更新")

    # ===== 保存或更新数据 =====
    records = []
    updated_count = 0
    inserted_count = 0
    matched_count = len(account_stats)

    for account_name, stats in account_stats.items():
        # 计算平均时间
        if stats["valid_time_count"] > 0:
            avg_time_seconds = stats["total_time_seconds"] // stats["valid_time_count"]
        else:
            avg_time_seconds = 0

        avg_time_str = format_seconds_to_time(avg_time_seconds)

        employee_account_id = stats["employee_account_id"]

        # ===== 检查是否已存在（精确匹配账号）=====
        existing = existing_records.get(account_name)

        if existing:
            # 更新现有记录
            existing.value = stats["total_orders"]
            existing.avg_time_seconds = avg_time_seconds
            existing.avg_time_str = avg_time_str
            existing.raw_data = {
                "total_orders": stats["total_orders"],
                "total_time_seconds": stats["total_time_seconds"],
                "valid_time_count": stats["valid_time_count"],
                "avg_time_seconds": avg_time_seconds,
                "upload_time": get_beijing_now().isoformat(),
                "upload_shift": shift,
                "employee_shift": stats.get("employee_shift"),
                "updated_from_batch": batch_id,
                "previous_value": existing.value,
                "upload_date": upload_date,  # ✅ 记录用户选择的日期
            }
            records.append(existing)
            updated_count += 1
            logger.debug(
                f"更新记录: {account_name} - 笔数: {stats['total_orders']} (原: {existing.value})"
            )
        else:
            # 创建新记录
            data_record = SiteDataRecord(
                site_id=site.id,
                site_code=site.code,
                employee_account_id=employee_account_id,
                account_name=account_name,
                shift=shift,
                date=stat_date_start_utc,
                value=stats["total_orders"],
                avg_time_seconds=avg_time_seconds,
                avg_time_str=avg_time_str,
                raw_data={
                    "total_orders": stats["total_orders"],
                    "total_time_seconds": stats["total_time_seconds"],
                    "valid_time_count": stats["valid_time_count"],
                    "avg_time_seconds": avg_time_seconds,
                    "upload_time": get_beijing_now().isoformat(),
                    "upload_shift": shift,
                    "employee_shift": stats.get("employee_shift"),
                    "upload_date": upload_date,  # ✅ 记录用户选择的日期
                },
                batch_id=batch_id,
                uploaded_by=user_id,
            )
            db.add(data_record)
            records.append(data_record)
            inserted_count += 1
            logger.debug(f"新增记录: {account_name} - 笔数: {stats['total_orders']}")

    db.commit()

    logger.info(f"保存完成: 新增 {inserted_count} 条, 更新 {updated_count} 条")

    # 构建返回数据
    stats_data = {
        "success": True,
        "site_code": site.code,
        "site_name": site.name,
        "total_records": total_records,
        "total_accounts": len(account_stats),
        "matched_count": matched_count,
        "unmatched_count": 0,
        "unmatched_accounts": [],
        "skipped_by_shift": skipped_by_shift,
        "skipped_unconfigured": skipped_unconfigured,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "shift": shift,
        "date": upload_date or stat_date.strftime("%Y-%m-%d"),  # ✅ 返回用户选择的日期
        "details": [],
    }

    for account_name, stats in account_stats.items():
        if stats["valid_time_count"] > 0:
            avg_seconds = stats["total_time_seconds"] // stats["valid_time_count"]
        else:
            avg_seconds = 0

        stats_data["details"].append(
            {
                "account_name": account_name,
                "employee_name": employee_names.get(account_name, account_name),
                "employee_account_id": stats["employee_account_id"],
                "is_matched": True,
                "employee_shift": stats.get("employee_shift"),
                "upload_shift": shift,
                "is_shift_matched": stats.get("employee_shift") == shift,
                "order_count": stats["total_orders"],
                "total_time_seconds": stats["total_time_seconds"],
                "valid_time_count": stats["valid_time_count"],
                "avg_time_seconds": avg_seconds,
                "avg_time_str": format_seconds_to_time(avg_seconds),
            }
        )

    return stats_data, matched_count, 0


# ==================== 数据查询 API ====================


@router.get("/data")
def get_site_data(
    site_id: Optional[int] = None,
    employee_account_id: Optional[int] = None,
    account_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    batch_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取站点数据"""
    query = db.query(SiteDataRecord)

    if site_id:
        query = query.filter(SiteDataRecord.site_id == site_id)
    if employee_account_id:
        query = query.filter(SiteDataRecord.employee_account_id == employee_account_id)
    if account_name:
        query = query.filter(SiteDataRecord.account_name.ilike(f"%{account_name}%"))
    if batch_id:
        query = query.filter(SiteDataRecord.batch_id == batch_id)
    if start_date:
        start = parse_beijing_datetime(f"{start_date} 00:00:00")
        if start:
            start_utc = make_naive(to_utc_time(start))
            query = query.filter(SiteDataRecord.date >= start_utc)
    if end_date:
        end = parse_beijing_datetime(f"{end_date} 23:59:59")
        if end:
            end_utc = make_naive(to_utc_time(end))
            query = query.filter(SiteDataRecord.date <= end_utc)

    total = query.count()
    records = (
        query.order_by(desc(SiteDataRecord.date), SiteDataRecord.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [r.to_dict() for r in records]

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(items)) < total,
    }


# server_site_routes.py - 完整的 summary 接口


@router.get("/summary")
def get_site_summary(
    site_id: Optional[int] = None,
    shift: Optional[str] = None,
    employee_account_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取站点数据汇总 - 只返回指定日期范围内有数据的员工"""
    from sqlalchemy import func, and_
    import logging

    logger = logging.getLogger(__name__)

    # ✅ 打印接收到的参数
    logger.info(f"=== 收到汇总请求 ===")
    logger.info(f"site_id: {site_id}")
    logger.info(f"shift: {shift}")
    logger.info(f"start_date: {start_date}")
    logger.info(f"end_date: {end_date}")

    # 构建基础查询 - ✅ 使用 INNER JOIN，只返回有数据的记录
    query = (
        db.query(
            SiteEmployeeAccount.name.label("employee_name"),
            SiteEmployeeAccount.account_name,
            Site.code.label("site_code"),
            func.sum(SiteDataRecord.value).label("total_value"),
            func.avg(SiteDataRecord.avg_time_seconds).label("avg_time_seconds"),
        )
        .join(
            SiteDataRecord, SiteDataRecord.employee_account_id == SiteEmployeeAccount.id
        )  # ✅ INNER JOIN
        .join(Site, SiteDataRecord.site_id == Site.id)
    )

    # 应用筛选条件
    if site_id:
        query = query.filter(SiteDataRecord.site_id == site_id)
        logger.info(f"过滤 site_id: {site_id}")

    if shift:
        query = query.filter(SiteDataRecord.shift == shift)
        logger.info(f"过滤 shift: {shift}")

    if employee_account_id:
        query = query.filter(SiteEmployeeAccount.id == employee_account_id)

    # ✅ 关键：日期筛选
    if start_date:
        # 确保 start_date 包含时间
        if " " not in start_date:
            start_date = f"{start_date} 00:00:00"
        start = parse_beijing_datetime(start_date)
        if start:
            start_utc = make_naive(to_utc_time(start))
            query = query.filter(SiteDataRecord.date >= start_utc)
            logger.info(f"过滤 start_date: {start_date} -> UTC: {start_utc}")

    if end_date:
        if " " not in end_date:
            end_date = f"{end_date} 23:59:59"
        end = parse_beijing_datetime(end_date)
        if end:
            end_utc = make_naive(to_utc_time(end))
            query = query.filter(SiteDataRecord.date <= end_utc)
            logger.info(f"过滤 end_date: {end_date} -> UTC: {end_utc}")

    # 如果没有日期范围，返回空
    if not start_date and not end_date:
        logger.warning("没有日期范围，返回空数据")
        return {"items": [], "total": 0, "site_columns": []}

    # 执行查询
    results = query.group_by(
        SiteEmployeeAccount.name, SiteEmployeeAccount.account_name, Site.code
    ).all()

    logger.info(f"查询到 {len(results)} 条原始记录")

    # 如果没有数据，返回空
    if not results:
        logger.info("没有找到数据，返回空")
        return {"items": [], "total": 0, "site_columns": []}

    # 按员工姓名聚合（后续处理保持不变）
    employee_map = {}
    for row in results:
        emp_name = row.employee_name
        if emp_name not in employee_map:
            employee_map[emp_name] = {
                "employee_name": emp_name,
                "accounts": set(),
                "sites": {},
                "total_value": 0,
                "total_weighted_time": 0,
                "total_weight": 0,
            }

        if row.account_name:
            employee_map[emp_name]["accounts"].add(row.account_name)

        site_code = row.site_code
        site_value = row.total_value or 0
        site_avg = int(row.avg_time_seconds) if row.avg_time_seconds else 0

        if site_code in employee_map[emp_name]["sites"]:
            existing = employee_map[emp_name]["sites"][site_code]
            new_value = existing["value"] + site_value
            if new_value > 0:
                existing_total_time = existing["value"] * existing["avg_time_seconds"]
                new_total_time = site_value * site_avg
                new_avg = (existing_total_time + new_total_time) // new_value
            else:
                new_avg = 0
            employee_map[emp_name]["sites"][site_code] = {
                "value": new_value,
                "avg_time_seconds": new_avg,
                "avg_time_str": format_seconds_to_time(new_avg),
            }
        else:
            employee_map[emp_name]["sites"][site_code] = {
                "value": site_value,
                "avg_time_seconds": site_avg,
                "avg_time_str": format_seconds_to_time(site_avg),
            }

        employee_map[emp_name]["total_value"] += site_value
        if site_avg > 0 and site_value > 0:
            employee_map[emp_name]["total_weighted_time"] += site_avg * site_value
            employee_map[emp_name]["total_weight"] += site_value

    # 构建返回数据
    items = []
    for emp_name, emp_data in employee_map.items():
        if emp_data["total_weight"] > 0:
            total_avg = emp_data["total_weighted_time"] // emp_data["total_weight"]
        else:
            total_avg = 0

        accounts_str = ", ".join(sorted(emp_data["accounts"]))

        items.append(
            {
                "employee_name": emp_data["employee_name"],
                "account_name": accounts_str,
                "sites": emp_data["sites"],
                "total_value": emp_data["total_value"],
                "total_avg_seconds": total_avg,
                "total_avg_time": format_seconds_to_time(total_avg),
            }
        )

    items.sort(key=lambda x: x["employee_name"])

    all_sites = set()
    for emp in items:
        for site_code in emp["sites"].keys():
            all_sites.add(site_code)
    all_sites = sorted(list(all_sites))

    logger.info(f"最终返回 {len(items)} 个员工，站点列: {all_sites}")

    return {"items": items, "total": len(items), "site_columns": all_sites}


@router.get("/stats")
def get_site_stats(
    site_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取站点统计概览"""
    query = db.query(SiteDataRecord)
    if site_id:
        query = query.filter(SiteDataRecord.site_id == site_id)

    total_records = query.count()
    total_value = query.with_entities(func.sum(SiteDataRecord.value)).scalar() or 0

    active_accounts = db.query(SiteDataRecord.employee_account_id).filter(
        SiteDataRecord.employee_account_id.isnot(None)
    )
    if site_id:
        active_accounts = active_accounts.filter(SiteDataRecord.site_id == site_id)
    active_accounts = active_accounts.distinct().count()

    total_accounts_query = db.query(SiteEmployeeAccount)
    if site_id:
        total_accounts_query = total_accounts_query.filter(
            SiteEmployeeAccount.site_id == site_id
        )
    total_accounts = total_accounts_query.count()

    return {
        "total_records": total_records,
        "total_value": total_value,
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
    }


@router.get("/upload-batches")
def get_upload_batches(
    site_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取上传批次列表"""
    query = db.query(UploadBatch)

    if site_id:
        query = query.filter(UploadBatch.site_id == site_id)

    batches = query.order_by(desc(UploadBatch.created_at)).limit(limit).all()

    items = []
    for batch in batches:
        item = batch.to_dict()
        site = db.query(Site).filter(Site.id == batch.site_id).first()
        if site:
            item["site_code"] = site.code
            item["site_name"] = site.name
        items.append(item)

    return {"items": items, "total": len(items)}


@router.delete("/data/batch/{batch_id}")
def delete_batch_data(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:cleanup")),
):
    """删除指定批次的数据"""
    deleted = (
        db.query(SiteDataRecord).filter(SiteDataRecord.batch_id == batch_id).delete()
    )

    batch = db.query(UploadBatch).filter(UploadBatch.batch_id == batch_id).first()
    if batch:
        batch.status = "deleted"
        db.commit()

    db.commit()

    logger.info(
        f"批次数据删除: {batch_id}, 删除 {deleted} 条记录 by {current_user.username}"
    )
    return {"message": f"已删除 {deleted} 条记录"}


@router.delete("/data/clear")
def clear_all_data(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:cleanup")),
):
    """清空所有站点数据"""
    deleted = db.query(SiteDataRecord).delete()
    db.query(UploadBatch).delete()
    db.commit()

    logger.info(f"清空所有站点数据: {deleted} 条记录 by {current_user.username}")
    return {"message": f"已清空 {deleted} 条记录"}


@router.delete("/data/clear-by-date")
def clear_data_by_date(
    site_id: int,
    shift: str,
    date: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:cleanup")),
):
    """清除指定站点、班次、日期的数据"""
    from server_timezone import to_utc_time, make_naive, BEIJING_TZ
    from datetime import datetime, timedelta

    # 验证参数
    if shift not in ["day", "night"]:
        raise HTTPException(status_code=400, detail="班次必须是 day 或 night")

    # 验证站点是否存在
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="站点不存在")

    # 解析日期
    try:
        # 创建北京时间的日期对象
        beijing_date = datetime.strptime(date, "%Y-%m-%d")
        # 添加北京时间时区
        beijing_date = beijing_date.replace(tzinfo=BEIJING_TZ)
        # 转换为 UTC 时间
        utc_date = to_utc_time(beijing_date)
        # 转为 naive（数据库存储格式）
        date_start_utc = make_naive(utc_date)
        date_end_utc = date_start_utc + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

    # 先查询将要删除的数据条数
    count_query = db.query(SiteDataRecord).filter(
        SiteDataRecord.site_id == site_id,
        SiteDataRecord.shift == shift,
        SiteDataRecord.date >= date_start_utc,
        SiteDataRecord.date < date_end_utc,
    )
    count = count_query.count()

    if count == 0:
        return {
            "message": "没有找到需要删除的数据",
            "deleted_count": 0,
            "site_id": site_id,
            "shift": shift,
            "date": date,
        }

    # 执行删除
    deleted = count_query.delete()
    db.commit()

    logger.info(
        f"清除数据: site_id={site_id}, site_code={site.code}, shift={shift}, date={date}, 删除 {deleted} 条记录 by {current_user.username}"
    )

    return {
        "message": f"已清除 {deleted} 条记录",
        "deleted_count": deleted,
        "site_id": site_id,
        "site_code": site.code,
        "shift": shift,
        "date": date,
    }


# ==================== 外部数据同步 API ====================
@router.post("/sync")
async def sync_external_data(
    site_id: int = Form(...),
    shift: str = Form(...),
    date: str = Form(...),
    data: str = Form(...),
    start_time: Optional[str] = Form(None),
    end_time: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """同步外部系统数据到本地"""
    import json
    import logging

    logger = logging.getLogger(__name__)

    # 打印接收到的参数
    logger.info("=" * 50)
    logger.info("收到同步请求:")
    logger.info(f"  site_id: {site_id}")
    logger.info(f"  shift: {shift}")
    logger.info(f"  date: {date}")
    logger.info(f"  start_time: {start_time}")
    logger.info(f"  end_time: {end_time}")
    logger.info(f"  data keys: {list(json.loads(data).keys()) if data else 'empty'}")
    logger.info("=" * 50)

    try:
        # 验证站点
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            raise HTTPException(status_code=404, detail="站点不存在")

        # 验证班次
        if shift not in ["day", "night", "manual"]:
            raise HTTPException(
                status_code=400, detail="班次必须是 day、night 或 manual"
            )

        # 解析数据
        try:
            external_data = json.loads(data)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"数据格式错误: {str(e)}")

        # 解析统计日期/时间
        try:
            if shift == "manual" and start_time and end_time:
                # 手动模式
                try:
                    stat_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    stat_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
                stat_start = stat_start.replace(tzinfo=BEIJING_TZ)

                try:
                    stat_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    stat_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M")
                stat_end = stat_end.replace(tzinfo=BEIJING_TZ)

                stat_date = stat_start
                logger.info(f"手动模式时间范围: {stat_start} 至 {stat_end}")
            else:
                # 自动模式
                stat_date = datetime.strptime(date, "%Y-%m-%d")
                stat_date = stat_date.replace(tzinfo=BEIJING_TZ)
                logger.info(f"自动模式日期: {stat_date}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"日期/时间格式错误: {str(e)}")

        # 获取员工账号映射
        accounts = (
            db.query(SiteEmployeeAccount)
            .filter(
                SiteEmployeeAccount.site_id == site.id,
                SiteEmployeeAccount.is_active == True,
            )
            .all()
        )
        account_map = {acc.account_name: acc.id for acc in accounts}
        employee_names = {acc.account_name: acc.name for acc in accounts}

        # 创建批次记录
        batch_id = f"sync_{site.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        batch = UploadBatch(
            batch_id=batch_id,
            site_id=site_id,
            filename=f"sync_{date}.json",
            file_type="json",
            status="processing",
            uploaded_by=current_user.id,
        )
        db.add(batch)
        db.commit()

        # 保存数据
        records_saved = 0
        matched_count = 0
        unmatched_accounts = set()

        for account_name, stats in external_data.items():
            employee_account_id = account_map.get(account_name)

            if employee_account_id:
                matched_count += 1
            else:
                unmatched_accounts.add(account_name)

            valid_count = stats.get("valid_time_count", 0)
            if valid_count > 0:
                avg_seconds = stats["total_time_seconds"] // valid_count
            else:
                avg_seconds = 0

            avg_time_str = format_seconds_to_time(avg_seconds)

            record = SiteDataRecord(
                site_id=site.id,
                site_code=site.code,
                employee_account_id=employee_account_id,
                account_name=account_name,
                shift=shift,
                date=make_naive(stat_date),
                value=stats["total_orders"],
                avg_time_seconds=avg_seconds,
                avg_time_str=avg_time_str,
                raw_data={
                    "total_orders": stats["total_orders"],
                    "total_time_seconds": stats["total_time_seconds"],
                    "valid_time_count": valid_count,
                    "sync_time": get_beijing_now().isoformat(),
                    "source": "external_api",
                },
                batch_id=batch_id,
                uploaded_by=current_user.id,
            )
            db.add(record)
            records_saved += 1

        batch.record_count = records_saved
        batch.matched_count = matched_count
        batch.unmatched_count = len(unmatched_accounts)
        batch.status = "completed"

        db.commit()

        logger.info(f"同步成功: {records_saved} 条记录")

        return {
            "success": True,
            "batch_id": batch_id,
            "records_saved": records_saved,
            "matched_count": matched_count,
            "unmatched_count": len(unmatched_accounts),
            "unmatched_accounts": list(unmatched_accounts),
            "message": f"成功同步 {records_saved} 条记录",
        }

    except Exception as e:
        logger.error(f"同步失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


@router.get("/stacked-summary")
def get_stacked_site_summary(
    site_id: Optional[int] = None,
    shift: Optional[str] = None,
    employee_account_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    获取按日期堆叠的站点数据汇总（前端聚合版本）
    """
    import logging
    from datetime import timedelta

    logger = logging.getLogger(__name__)

    logger.info("=== 堆叠接口收到参数 ===")
    logger.info(f"site_id: {site_id}")
    logger.info(f"employee_account_id: {employee_account_id}")
    logger.info(f"start_date: {start_date}")
    logger.info(f"end_date: {end_date}")
    logger.info(f"shift: {shift}")

    # ================= 构建查询 =================
    query = db.query(
        SiteDataRecord.date,
        SiteDataRecord.raw_data,
        SiteEmployeeAccount.id.label("employee_id"),
        SiteEmployeeAccount.name.label("employee_name"),
        SiteEmployeeAccount.account_name,
        SiteDataRecord.site_code,
        SiteDataRecord.value,
        SiteDataRecord.avg_time_seconds,
        SiteDataRecord.avg_time_str,
    ).join(
        SiteEmployeeAccount,
        SiteDataRecord.employee_account_id == SiteEmployeeAccount.id,
    )

    if site_id:
        query = query.filter(SiteDataRecord.site_id == site_id)

    if shift:
        query = query.filter(SiteDataRecord.shift == shift)

    if employee_account_id:
        query = query.filter(SiteEmployeeAccount.id == employee_account_id)

    # ================= 日期处理 =================
    if start_date:
        if " " not in start_date:
            start_date = f"{start_date} 00:00:00"
        start = parse_beijing_datetime(start_date)
        if start:
            start_utc = make_naive(to_utc_time(start))
            query = query.filter(SiteDataRecord.date >= start_utc)

    if end_date:
        if " " not in end_date:
            end_date = f"{end_date} 23:59:59"
        end = parse_beijing_datetime(end_date)
        if end:
            end_utc = make_naive(to_utc_time(end))
            query = query.filter(SiteDataRecord.date <= end_utc)

    # 没有时间范围直接返回空（避免全表扫描）
    if not start_date and not end_date:
        return {"items": [], "site_columns": [], "total": 0}

    # ================= 查询 =================
    results = query.order_by(SiteDataRecord.date.desc(), SiteEmployeeAccount.name).all()

    if not results:
        return {"items": [], "site_columns": [], "total": 0}

    # ================= 获取站点列 =================
    site_codes_in_data = {row.site_code for row in results if row.site_code}

    all_sites = (
        db.query(Site.code, Site.sort_order)
        .filter(Site.is_active == True, Site.code.in_(site_codes_in_data))
        .order_by(Site.sort_order)
        .all()
    )

    site_columns = [s[0] for s in all_sites]

    # ================= 数据转换 =================
    items = []

    for row in results:
        # ---------- 日期处理 ----------
        upload_date = None
        if row.raw_data and isinstance(row.raw_data, dict):
            upload_date = row.raw_data.get("upload_date")

        if upload_date:
            date_str = upload_date
        else:
            utc_time = row.date
            beijing_time = utc_time + timedelta(hours=8)
            date_str = beijing_time.strftime("%Y-%m-%d")

        # ---------- employee_id 安全处理（关键） ----------
        if row.employee_id is not None:
            employee_id_val = row.employee_id
        else:
            # ⚠️ 必须保证唯一且不与数字冲突
            employee_id_val = f"virtual_{row.account_name}"
            logger.warning(f"employee_id 为 None，使用虚拟ID: {employee_id_val}")

        # ---------- 组装数据 ----------
        items.append(
            {
                "date": date_str,
                "employee_id": employee_id_val,
                "employee_name": row.employee_name or row.account_name,
                "account_name": row.account_name,
                "site_code": row.site_code,
                "value": row.value or 0,
                "avg_time_seconds": row.avg_time_seconds or 0,
                "avg_time_str": row.avg_time_str or "-",
            }
        )

    # ================= 返回 =================
    return {
        "items": items,
        "site_columns": site_columns,
        "total": len(items),
    }
