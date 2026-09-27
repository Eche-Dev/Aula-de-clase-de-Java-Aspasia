"""Router v1."""

from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    announcements,
    attendance,
    auth,
    calendar,
    calendar_inst,
    course_chat,
    courses,
    health,
    messages,
    phase3,
    phase_c,
    phase_d,
    public,
    rubrics,
    sections,
    student,
    superadmin,
    teacher,
    webhooks,
    work,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(public.router)
api_router.include_router(webhooks.router)
api_router.include_router(courses.router)
api_router.include_router(work.router)
api_router.include_router(sections.router)
api_router.include_router(announcements.router)
api_router.include_router(admin.router)
api_router.include_router(rubrics.router)
api_router.include_router(attendance.router)
api_router.include_router(calendar.router)
api_router.include_router(calendar_inst.router)
api_router.include_router(phase3.router)
api_router.include_router(phase_c.router)
api_router.include_router(phase_d.router)
api_router.include_router(messages.router)
api_router.include_router(course_chat.router)
api_router.include_router(student.router)
api_router.include_router(teacher.router)
api_router.include_router(superadmin.router)

__all__ = ["api_router"]
