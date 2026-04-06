# server_attendance.py - 完整修复版

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pydantic import BaseModel as PydanticBaseModel
from server_auth import PermissionChecker
from server_permissions import PermissionCode

from server_database import get_db
from server_auth import get_current_active_user, PermissionChecker
import server_models as models
from server_timezone import get_beijing_now

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["考勤管理"])


# ==================== Pydantic Schemas ====================


class AttendanceEmployeeCreate(PydanticBaseModel):
    """创建考勤员工"""

    name: str
    employee_id: str
    hire_date: Optional[str] = None
    work_location: str = "现场"
    position: Optional[str] = None  # 添加岗位字段


class AttendanceEmployeeUpdate(PydanticBaseModel):
    """更新考勤员工"""

    name: Optional[str] = None
    employee_id: Optional[str] = None
    hire_date: Optional[str] = None
    work_location: Optional[str] = None
    position: Optional[str] = None  # 添加岗位字段


class AttendanceRecordBatchSave(PydanticBaseModel):
    """批量保存考勤记录"""

    year_month: str
    data: Dict[
        str, Dict[str, Dict[str, str]]
    ]  # {employee_id: {date: {status, remark}}}


# ==================== 评分记录 Schema ====================


class ScoreRecord(PydanticBaseModel):
    """加减分记录"""

    date: str
    score: int
    reason: str


class PerformanceItem(PydanticBaseModel):
    """单个员工绩效考核"""

    employee_id: int
    employee_name: str
    position: Optional[str] = None
    base_score: int = 10
    score_records: List[ScoreRecord] = []
    total_score: int = 10
    grade: str = "合格"


class PerformanceBatchSave(PydanticBaseModel):
    """批量保存绩效考核"""

    month: str
    items: List[PerformanceItem]


class BatchEmployeesRequest(PydanticBaseModel):
    """批量获取员工考勤请求"""

    year_month: str
    employee_ids: List[int]


# ==================== 员工管理 API ====================
@router.get("/attendance/employees")
def get_attendance_employees(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        PermissionChecker(PermissionCode.ATTENDANCE_VIEW.value)
    ),
):
    """获取考勤员工列表（支持分页和搜索）"""
    query = db.query(models.AttendanceEmployee)

    # 搜索过滤
    if search:
        query = query.filter(models.AttendanceEmployee.name.ilike(f"%{search}%"))

    # 获取总数
    total = query.count()

    # 分页查询
    employees = (
        query.order_by(models.AttendanceEmployee.hire_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [e.to_dict() for e in employees]

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/attendance/employees")
def create_attendance_employee(
    data: AttendanceEmployeeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        PermissionChecker(PermissionCode.ATTENDANCE_EDIT.value)
    ),
):
    """创建考勤员工"""
    # 检查 employee_id 是否已存在
    existing = (
        db.query(models.AttendanceEmployee)
        .filter(models.AttendanceEmployee.employee_id == data.employee_id)
        .first()
    )

    if existing:
        raise HTTPException(status_code=400, detail="员工ID已存在")

    hire_date = None
    if data.hire_date:
        hire_date = datetime.strptime(data.hire_date, "%Y-%m-%d")

    employee = models.AttendanceEmployee(
        name=data.name,
        employee_id=data.employee_id,
        hire_date=hire_date,
        work_location=data.work_location,
        position=data.position,  # ✅ 添加这一行
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    logger.info(
        f"考勤员工创建: {data.name} (岗位: {data.position}) by {current_user.username}"
    )

    result = employee.to_dict()
    # result["position"] = data.position  # 不需要了，因为 to_dict 会返回 position
    return result


@router.put("/attendance/employees/{employee_id}")
def update_attendance_employee(
    employee_id: int,
    data: AttendanceEmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """更新考勤员工"""
    employee = (
        db.query(models.AttendanceEmployee)
        .filter(models.AttendanceEmployee.id == employee_id)
        .first()
    )

    if not employee:
        raise HTTPException(status_code=404, detail="员工不存在")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        if key == "hire_date" and value:
            value = datetime.strptime(value, "%Y-%m-%d")
        setattr(employee, key, value)

    db.commit()
    db.refresh(employee)

    logger.info(f"考勤员工更新: {employee.name} by {current_user.username}")
    return employee.to_dict()


@router.delete("/attendance/employees/{employee_id}")
def delete_attendance_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """删除考勤员工"""
    employee = (
        db.query(models.AttendanceEmployee)
        .filter(models.AttendanceEmployee.id == employee_id)
        .first()
    )

    if not employee:
        raise HTTPException(status_code=404, detail="员工不存在")

    # 删除关联的考勤记录
    db.query(models.AttendanceRecord).filter(
        models.AttendanceRecord.employee_id == employee_id
    ).delete()

    # 删除关联的绩效考核记录
    if hasattr(models, "Performance"):
        db.query(models.Performance).filter(
            models.Performance.employee_id == employee_id
        ).delete()

    db.delete(employee)
    db.commit()

    logger.info(f"考勤员工删除: {employee.name} by {current_user.username}")
    return {"message": "员工已删除"}


# ==================== 考勤记录 API ====================


@router.get("/attendance/records/batch")
def get_attendance_records_batch(
    year_month: str,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """批量获取月度考勤记录"""
    try:
        start_date = datetime.strptime(f"{year_month}-01", "%Y-%m-%d")
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1)

        query = db.query(models.AttendanceRecord).filter(
            models.AttendanceRecord.record_date >= start_date,
            models.AttendanceRecord.record_date < end_date,
        )

        if employee_id:
            query = query.filter(models.AttendanceRecord.employee_id == employee_id)

        records = query.all()

        result = {}
        for r in records:
            emp_id = r.employee_id
            date_str = r.record_date.strftime("%Y-%m-%d")
            if emp_id not in result:
                result[emp_id] = {}
            result[emp_id][date_str] = {"status": r.status, "remark": r.remark}

        return {"data": result, "year_month": year_month}
    except Exception as e:
        logger.error(f"获取考勤记录失败: {e}")
        return {"data": {}, "year_month": year_month}


@router.post("/attendance/records/batch-by-employees")
def get_attendance_records_by_employees(
    request: BatchEmployeesRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """批量获取多个员工的考勤记录（性能优化版）"""
    try:
        # 解析月份范围
        start_date = datetime.strptime(f"{request.year_month}-01", "%Y-%m-%d")
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1)

        # 一次性查询所有员工的考勤记录
        records = (
            db.query(models.AttendanceRecord)
            .filter(
                models.AttendanceRecord.employee_id.in_(request.employee_ids),
                models.AttendanceRecord.record_date >= start_date,
                models.AttendanceRecord.record_date < end_date,
            )
            .all()
        )

        # 构建返回数据
        result = {}
        for r in records:
            emp_id = r.employee_id
            date_str = r.record_date.strftime("%Y-%m-%d")
            if emp_id not in result:
                result[emp_id] = {}
            result[emp_id][date_str] = {"status": r.status, "remark": r.remark}

        logger.info(
            f"批量获取考勤记录成功: {request.year_month}, 员工数={len(request.employee_ids)}, 记录数={len(records)}"
        )
        return {"data": result, "year_month": request.year_month}

    except Exception as e:
        logger.error(f"批量获取考勤记录失败: {e}", exc_info=True)
        return {"data": {}, "year_month": request.year_month}


@router.post("/attendance/records/batch")
def save_attendance_records_batch(
    data: AttendanceRecordBatchSave,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        PermissionChecker(PermissionCode.ATTENDANCE_EDIT.value)
    ),
):
    """批量保存月度考勤记录"""
    try:
        # 获取所有有效的员工ID映射
        employees_map = {}
        all_employees = db.query(models.AttendanceEmployee).all()
        for emp in all_employees:
            employees_map[str(emp.id)] = emp.id
            employees_map[emp.id] = emp.id

        logger.info(f"有效的员工ID: {list(employees_map.keys())}")

        saved_count = 0
        for emp_id_str, records in data.data.items():
            # 验证员工ID是否存在
            if emp_id_str not in employees_map:
                logger.warning(
                    f"员工ID {emp_id_str} 不在 attendance_employees 表中，跳过"
                )
                continue

            emp_id = employees_map[emp_id_str]

            for date_str, record_data in records.items():
                try:
                    record_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError as e:
                    logger.warning(f"日期格式错误: {date_str}, {e}")
                    continue

                status = record_data.get("status", "work")
                remark = record_data.get("remark", "")

                existing = (
                    db.query(models.AttendanceRecord)
                    .filter(
                        models.AttendanceRecord.employee_id == emp_id,
                        models.AttendanceRecord.record_date == record_date,
                    )
                    .first()
                )

                if existing:
                    existing.status = status
                    existing.remark = remark
                    existing.updated_at = get_beijing_now()
                else:
                    new_record = models.AttendanceRecord(
                        employee_id=emp_id,
                        record_date=record_date,
                        status=status,
                        remark=remark,
                    )
                    db.add(new_record)

                saved_count += 1

        db.commit()
        logger.info(f"批量保存考勤成功: {data.year_month}, 保存 {saved_count} 条记录")
        return {
            "message": "保存成功",
            "year_month": data.year_month,
            "saved_count": saved_count,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"批量保存考勤失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 汇总 API ====================


@router.get("/attendance/summary")
def get_attendance_summary(
    year_month: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取月度考勤汇总"""
    try:
        start_date = datetime.strptime(f"{year_month}-01", "%Y-%m-%d")
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1)

        employees = db.query(models.AttendanceEmployee).all()
        records = (
            db.query(models.AttendanceRecord)
            .filter(
                models.AttendanceRecord.record_date >= start_date,
                models.AttendanceRecord.record_date < end_date,
            )
            .all()
        )

        # 按员工分组统计
        employee_stats = {}
        for emp in employees:
            employee_stats[emp.id] = {
                "id": emp.id,
                "name": emp.name,
                "employee_id": emp.employee_id,
                "hire_date": emp.hire_date,
                "work_location": emp.work_location,
                "work_days": 0,
                "rest_days": 0,
                "leave_days": 0,
                "absent_days": 0,
                "off_post_days": 0,
                "resigned_days": 0,
            }

        for r in records:
            if r.employee_id in employee_stats:
                status = r.status
                if status == "work":
                    employee_stats[r.employee_id]["work_days"] += 1
                elif status == "rest_half" or status == "rest_full":
                    employee_stats[r.employee_id]["rest_days"] += (
                        0.5 if status == "rest_half" else 1
                    )
                elif status == "leave":
                    employee_stats[r.employee_id]["leave_days"] += 0.5
                elif status == "absent":
                    employee_stats[r.employee_id]["absent_days"] += 1
                elif status == "off_post":
                    employee_stats[r.employee_id]["off_post_days"] += 1
                elif status == "resigned":
                    employee_stats[r.employee_id]["resigned_days"] += 1

        items = []
        total_work_days = 0
        total_leave_rest_days = 0

        for emp_id, stats in employee_stats.items():
            items.append(
                {
                    "id": stats["id"],
                    "name": stats["name"],
                    "employee_id": stats["employee_id"],
                    "hire_date": (
                        stats["hire_date"].strftime("%Y-%m-%d")
                        if stats["hire_date"]
                        else ""
                    ),
                    "work_location": stats["work_location"],
                    "work_days": stats["work_days"],
                    "rest_days": stats["rest_days"],
                    "leave_days": stats["leave_days"],
                    "absent_days": stats["absent_days"],
                    "off_post_days": stats["off_post_days"],
                    "resigned_days": stats["resigned_days"],
                }
            )

            total_work_days += stats["work_days"]
            total_leave_rest_days += stats["rest_days"] + stats["leave_days"]

        stats_summary = {
            "totalEmployees": len(items),
            "totalWorkDays": total_work_days,
            "totalLeaveRestDays": total_leave_rest_days,
            "avgAttendanceRate": (
                round(total_work_days / len(items) / 30 * 100) if items else 0
            ),
        }

        return {"items": items, "stats": stats_summary}
    except Exception as e:
        logger.error(f"获取汇总失败: {e}")
        return {"items": [], "stats": None}


# ==================== 绩效考核 API ====================


@router.get("/attendance/performance")
def get_performance(
    month: str,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取绩效考核数据"""
    try:
        # 检查 Performance 模型是否存在
        if not hasattr(models, "Performance"):
            logger.warning("Performance 模型不存在，返回空数据")
            return {"items": [], "total": 0}

        query = db.query(models.Performance).filter(models.Performance.month == month)

        if employee_id:
            query = query.filter(models.Performance.employee_id == employee_id)

        performances = query.all()

        items = []
        for p in performances:
            item = p.to_dict()
            items.append(item)

        # 如果某个员工没有绩效考核记录，返回默认数据
        all_employees = (
            db.query(models.AttendanceEmployee)
            .filter(models.AttendanceEmployee.is_active == True)
            .all()
        )

        existing_emp_ids = [p.employee_id for p in performances]
        for emp in all_employees:
            if emp.id not in existing_emp_ids:
                items.append(
                    {
                        "employee_id": emp.id,
                        "employee_name": emp.name,
                        "position": getattr(emp, "position", None),
                        "base_score": 10,
                        "score_records": [],
                        "total_score": 10,
                        "grade": "合格",
                        "month": month,
                    }
                )

        return {"items": items, "total": len(items)}

    except Exception as e:
        logger.error(f"获取绩效考核失败: {e}", exc_info=True)
        return {"items": [], "total": 0}


@router.post("/attendance/performance/batch")
def save_performance_batch(
    data: PerformanceBatchSave,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """批量保存绩效考核数据"""
    try:
        # 检查 Performance 模型是否存在
        if not hasattr(models, "Performance"):
            logger.warning("Performance 模型不存在，跳过保存")
            return {
                "message": "Performance 模型未创建",
                "month": data.month,
                "saved_count": 0,
            }

        logger.info(f"保存绩效考核数据: month={data.month}, items={len(data.items)}")

        saved_count = 0
        for item in data.items:
            # 查找是否已存在
            existing = (
                db.query(models.Performance)
                .filter(
                    models.Performance.employee_id == item.employee_id,
                    models.Performance.month == data.month,
                )
                .first()
            )

            # 转换 score_records 为字典格式
            score_records = []
            for record in item.score_records:
                score_records.append(
                    {
                        "date": record.date,
                        "score": record.score,
                        "reason": record.reason,
                    }
                )

            if existing:
                # 更新现有记录
                existing.total_score = item.total_score
                existing.grade = item.grade
                existing.score_records = score_records
                existing.updated_at = get_beijing_now()
            else:
                # 创建新记录
                new_performance = models.Performance(
                    employee_id=item.employee_id,
                    month=data.month,
                    total_score=item.total_score,
                    grade=item.grade,
                    score_records=score_records,
                )
                db.add(new_performance)

            saved_count += 1

        db.commit()
        logger.debug(f"批量保存绩效考核成功: {data.month}, 保存 {saved_count} 条记录")
        return {"message": "保存成功", "month": data.month, "saved_count": saved_count}

    except Exception as e:
        db.rollback()
        logger.error(f"批量保存绩效考核失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/attendance/performance/{performance_id}")
def delete_performance(
    performance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """删除绩效考核记录"""
    try:
        if not hasattr(models, "Performance"):
            raise HTTPException(status_code=404, detail="Performance 模型不存在")

        performance = (
            db.query(models.Performance)
            .filter(models.Performance.id == performance_id)
            .first()
        )

        if not performance:
            raise HTTPException(status_code=404, detail="绩效考核记录不存在")

        db.delete(performance)
        db.commit()

        logger.info(f"删除绩效考核: id={performance_id} by {current_user.username}")
        return {"message": "删除成功"}

    except Exception as e:
        db.rollback()
        logger.error(f"删除绩效考核失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/attendance/sync-employees")
def sync_employees_from_main(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """从主员工表同步数据到考勤员工表"""
    from server_models import Employee as MainEmployee

    main_employees = (
        db.query(MainEmployee).filter(MainEmployee.status == "active").all()
    )

    synced_count = 0
    for emp in main_employees:
        existing = (
            db.query(models.AttendanceEmployee)
            .filter(models.AttendanceEmployee.employee_id == emp.employee_id)
            .first()
        )

        if not existing:
            # 创建新考勤员工
            new_emp = models.AttendanceEmployee(
                name=emp.name,
                employee_id=emp.employee_id,
                hire_date=emp.created_at,
                work_location="现场",
                position=emp.position,
                is_active=True,
            )
            db.add(new_emp)
            synced_count += 1
        else:
            # 更新现有员工信息
            existing.name = emp.name
            existing.position = emp.position
            existing.hire_date = emp.created_at

    db.commit()

    return {
        "message": f"同步完成，新增 {synced_count} 名员工",
        "synced_count": synced_count,
    }


# ==================== 罚款管理 API ====================


class PenaltyRecordCreate(PydanticBaseModel):
    """创建罚款记录"""

    employee_id: int
    penalty_date: str
    amount: float
    category: str
    reason: str


class PenaltyRecordResponse(PydanticBaseModel):
    """罚款记录响应"""

    id: int
    employee_id: int
    employee_name: str
    position: Optional[str] = None
    penalty_date: str
    amount: float
    category: str
    reason: str
    created_by: Optional[str] = None
    created_at: str


@router.get("/attendance/penalty/records")
def get_penalty_records(
    month: Optional[str] = None,
    employee_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        PermissionChecker(PermissionCode.ATTENDANCE_VIEW.value)
    ),
):
    """获取罚款记录列表"""
    try:
        # 检查 PenaltyRecord 模型是否存在
        if not hasattr(models, "PenaltyRecord"):
            logger.warning("PenaltyRecord 模型不存在，返回空数据")
            return {
                "items": [],
                "total": 0,
                "stats": {
                    "totalAmount": 0,
                    "employeeCount": 0,
                    "recordCount": 0,
                    "avgAmount": 0,
                },
            }

        query = db.query(models.PenaltyRecord)

        if month:
            # 按月份筛选 (格式: YYYY-MM)
            start_date = datetime.strptime(f"{month}-01", "%Y-%m-%d")
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1)
            query = query.filter(
                models.PenaltyRecord.penalty_date >= start_date,
                models.PenaltyRecord.penalty_date < end_date,
            )

        if employee_id:
            query = query.filter(models.PenaltyRecord.employee_id == employee_id)

        total = query.count()
        records = (
            query.order_by(models.PenaltyRecord.penalty_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = []
        total_amount = 0
        employee_ids = set()

        for r in records:
            employee = (
                db.query(models.AttendanceEmployee)
                .filter(models.AttendanceEmployee.id == r.employee_id)
                .first()
            )
            items.append(
                {
                    "id": r.id,
                    "employee_id": r.employee_id,
                    "employee_name": employee.name if employee else "未知",
                    "position": employee.position if employee else None,
                    "penalty_date": r.penalty_date.strftime("%Y-%m-%d"),
                    "amount": r.amount,
                    "category": r.category,
                    "reason": r.reason,
                    "created_by": r.created_by,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
            total_amount += r.amount
            employee_ids.add(r.employee_id)

        stats = {
            "totalAmount": total_amount,
            "employeeCount": len(employee_ids),
            "recordCount": len(items),
            "avgAmount": round(total_amount / len(items), 2) if items else 0,
        }

        return {"items": items, "total": total, "stats": stats}

    except Exception as e:
        logger.error(f"获取罚款记录失败: {e}", exc_info=True)
        return {
            "items": [],
            "total": 0,
            "stats": {
                "totalAmount": 0,
                "employeeCount": 0,
                "recordCount": 0,
                "avgAmount": 0,
            },
        }


@router.post("/attendance/penalty/record")
def create_penalty_record(
    data: PenaltyRecordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """创建罚款记录"""
    try:
        # 检查 PenaltyRecord 模型是否存在
        if not hasattr(models, "PenaltyRecord"):
            logger.warning("PenaltyRecord 模型不存在")
            raise HTTPException(status_code=500, detail="PenaltyRecord 模型未创建")

        # 检查员工是否存在
        employee = (
            db.query(models.AttendanceEmployee)
            .filter(models.AttendanceEmployee.id == data.employee_id)
            .first()
        )
        if not employee:
            raise HTTPException(status_code=404, detail="员工不存在")

        penalty_date = datetime.strptime(data.penalty_date, "%Y-%m-%d")

        new_record = models.PenaltyRecord(
            employee_id=data.employee_id,
            penalty_date=penalty_date,
            amount=data.amount,
            category=data.category,
            reason=data.reason,
            created_by=current_user.username,
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        logger.info(
            f"罚款记录创建: 员工={employee.name}, 金额={data.amount} by {current_user.username}"
        )

        return {
            "id": new_record.id,
            "employee_id": new_record.employee_id,
            "employee_name": employee.name,
            "penalty_date": new_record.penalty_date.strftime("%Y-%m-%d"),
            "amount": new_record.amount,
            "category": new_record.category,
            "reason": new_record.reason,
            "created_by": new_record.created_by,
            "created_at": (
                new_record.created_at.isoformat() if new_record.created_at else None
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"创建罚款记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/attendance/penalty/records/{record_id}")
def delete_penalty_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(PermissionChecker("settings:update")),
):
    """删除罚款记录"""
    try:
        if not hasattr(models, "PenaltyRecord"):
            raise HTTPException(status_code=500, detail="PenaltyRecord 模型未创建")

        record = (
            db.query(models.PenaltyRecord)
            .filter(models.PenaltyRecord.id == record_id)
            .first()
        )
        if not record:
            raise HTTPException(status_code=404, detail="罚款记录不存在")

        db.delete(record)
        db.commit()

        logger.info(f"罚款记录删除: id={record_id} by {current_user.username}")
        return {"message": "删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除罚款记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
