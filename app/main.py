from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.api.v1.api import api_router

from app.core.config import settings
from app.core.security import create_access_token, get_current_user
from app.core.tasks import start_background_tasks, stop_background_tasks
from app.db.models.group import Group
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.group import GroupCreate, GroupUpdate
from app.schemas.setting import AppSettings
from app.schemas.user import UserCreate, UserUpdate
from app.services.group import (
    create_group,
    delete_group,
    get_group,
    get_groups,
    update_group,
)
from app.services.setting import get_app_settings, update_app_settings
from app.services.user import create_user, get_user, get_user_by_email, update_user

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Modern Usenet Indexer with FastAPI",
    version="0.5.4",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# Add middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert minutes to seconds
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# Include routers
app.include_router(api_router, prefix=settings.API_V1_STR)

# Import custom filters and context
from app.web.filters import filesizeformat, get_template_context, timeago

# Templates
templates = Jinja2Templates(directory="app/web/templates")

# Register custom filters
templates.env.filters["timeago"] = timeago
templates.env.filters["filesizeformat"] = filesizeformat


# Add global template variables
templates.env.globals.update(get_template_context())


# Helper functions for web routes
async def get_current_web_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get the current user from the session token"""
    token = request.session.get("access_token")
    if not token:
        return None

    try:
        user = await get_current_user(token=token, db=db)
        return user
    except HTTPException:
        # Token is invalid or expired
        request.session.pop("access_token", None)
        return None


def flash_message(request: Request, message: str, type: str = "info"):
    """Add a flash message to the session"""
    if "messages" not in request.session:
        request.session["messages"] = []
    request.session["messages"].append({"text": message, "type": type})


def get_flash_messages(request: Request):
    """Get and clear flash messages from the session"""
    messages = request.session.pop("messages", [])
    return messages


# Web routes
@app.get("/", response_class=HTMLResponse)
async def root():
    """
    Root endpoint that redirects to the web interface
    """
    return RedirectResponse(url="/browse")


@app.get("/browse", response_class=HTMLResponse)
async def browse(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Browse page
    """
    user = await get_current_web_user(request, db)
    return templates.TemplateResponse(
        "browse.html",
        {"request": request, "user": user, "messages": get_flash_messages(request)},
    )


# Authentication routes
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Login page
    """
    user = await get_current_web_user(request, db)
    if user:
        return RedirectResponse(url="/browse", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "login.html", {"request": request, "messages": get_flash_messages(request)}
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    remember: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    """
    Process login form
    """
    from app.core.security import verify_password
    from app.services.user import get_user_by_username

    # Try to find user by email first
    user = await get_user_by_email(db, email=login)

    # If not found by email, try by username
    if not user:
        user = await get_user_by_username(db, username=login)

    if not user or not verify_password(password, user.hashed_password):
        flash_message(request, "Invalid username/email or password", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if not user.is_active:
        flash_message(request, "Your account is inactive", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    if remember:
        access_token_expires = timedelta(days=30)  # Longer expiration for "remember me"

    access_token = create_access_token(user.id, expires_delta=access_token_expires)
    request.session["access_token"] = access_token

    # Update last login time
    user.last_login = datetime.utcnow()
    db.add(user)
    await db.commit()

    flash_message(request, f"Welcome back, {user.username}!", "success")
    return RedirectResponse(url="/browse", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Registration page
    """
    user = await get_current_web_user(request, db)
    if user:
        return RedirectResponse(url="/browse", status_code=status.HTTP_303_SEE_OTHER)

    # Check if registration is allowed
    app_settings = await get_app_settings(db)
    if not app_settings.allow_registration:
        flash_message(request, "Registration is currently disabled", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "register.html", {"request": request, "messages": get_flash_messages(request)}
    )


@app.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Process registration form
    """
    # Check if registration is allowed
    app_settings = await get_app_settings(db)
    if not app_settings.allow_registration:
        flash_message(request, "Registration is currently disabled", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Check if passwords match
    if password != confirm_password:
        flash_message(request, "Passwords do not match", "danger")
        return RedirectResponse(url="/register", status_code=status.HTTP_303_SEE_OTHER)

    # Check if user already exists
    existing_user = await get_user_by_email(db, email=email)
    if existing_user:
        flash_message(request, "A user with this email already exists", "danger")
        return RedirectResponse(url="/register", status_code=status.HTTP_303_SEE_OTHER)

    # Create user
    user_in = UserCreate(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )

    user = await create_user(db, user_in)

    # Log the user in
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(user.id, expires_delta=access_token_expires)
    request.session["access_token"] = access_token

    flash_message(
        request, "Registration successful! Welcome to NZB Indexer.", "success"
    )
    return RedirectResponse(url="/browse", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/logout")
async def logout(request: Request):
    """
    Logout user
    """
    request.session.pop("access_token", None)
    flash_message(request, "You have been logged out", "info")
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# Group routes
@app.get("/groups", response_class=HTMLResponse)
async def groups_page(
    request: Request,
    search: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """
    Groups listing page
    """
    user = await get_current_web_user(request, db)

    # Get groups with pagination
    per_page = 20
    skip = (page - 1) * per_page
    groups_data = await get_groups(
        db,
        skip=skip,
        limit=per_page,
        search=search,
        active=None,  # Show all groups, both active and inactive
    )

    # Create pagination object
    total = groups_data["total"]
    groups = groups_data["items"]

    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
        "has_prev": page > 1,
        "has_next": page < ((total + per_page - 1) // per_page),
        "prev_url": (
            f"/groups?page={page-1}&search={search}"
            if search and page > 1
            else f"/groups?page={page-1}" if page > 1 else None
        ),
        "next_url": (
            f"/groups?page={page+1}&search={search}"
            if search and page < ((total + per_page - 1) // per_page)
            else (
                f"/groups?page={page+1}"
                if page < ((total + per_page - 1) // per_page)
                else None
            )
        ),
        "iter_pages": lambda: range(1, ((total + per_page - 1) // per_page) + 1),
        "url_for_page": lambda p: (
            f"/groups?page={p}&search={search}" if search else f"/groups?page={p}"
        ),
    }

    return templates.TemplateResponse(
        "groups.html",
        {
            "request": request,
            "user": user,
            "groups": groups,
            "search": search,
            "pagination": pagination,
            "messages": get_flash_messages(request),
        },
    )


@app.get("/groups/{group_id}", response_class=HTMLResponse)
async def group_detail(
    request: Request, group_id: int, db: AsyncSession = Depends(get_db)
):
    """
    Group detail page
    """
    user = await get_current_web_user(request, db)
    group = await get_group(db, group_id)

    if not group:
        flash_message(request, "Group not found", "danger")
        return RedirectResponse(url="/groups", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "group_detail.html",
        {
            "request": request,
            "user": user,
            "group": group,
            "messages": get_flash_messages(request),
        },
    )


# Admin routes
async def admin_required(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """
    Check if the user is an admin
    """
    user = await get_current_web_user(request, db)
    if not user:
        flash_message(request, "Please login to access this page", "danger")
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )

    if not user.is_admin:
        flash_message(
            request, "You don't have permission to access this page", "danger"
        )
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/browse"},
        )

    return user


@app.get("/admin/groups", response_class=HTMLResponse)
async def admin_groups(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Admin groups management page
    """
    # Get active groups
    active_groups_data = await get_groups(db, active=True)
    active_groups = active_groups_data["items"]

    # Get inactive groups
    inactive_groups_data = await get_groups(db, active=False)
    inactive_groups = inactive_groups_data["items"]

    # Get backfill groups
    backfill_groups_data = await get_groups(db, backfill=True)
    backfill_groups = backfill_groups_data["items"]

    return templates.TemplateResponse(
        "admin/groups.html",
        {
            "request": request,
            "user": user,
            "active_groups": active_groups,
            "inactive_groups": inactive_groups,
            "backfill_groups": backfill_groups,
            "messages": get_flash_messages(request),
        },
    )


@app.get("/admin/groups/new", response_class=HTMLResponse)
async def admin_new_group(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Admin new group page
    """
    return templates.TemplateResponse(
        "admin/group_form.html",
        {
            "request": request,
            "user": user,
            "group": None,
            "messages": get_flash_messages(request),
        },
    )


@app.post("/admin/groups/new", response_class=HTMLResponse)
async def admin_create_group(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    active: bool = Form(False),
    backfill: bool = Form(False),
    min_files: int = Form(1),
    min_size: int = Form(0),
):
    """
    Admin create group
    """
    group_in = GroupCreate(
        name=name,
        description=description,
        active=active,
        backfill=backfill,
        min_files=min_files,
        min_size=min_size,
    )

    try:
        group = await create_group(db, group_in)
        flash_message(request, f"Group '{group.name}' created successfully", "success")
        return RedirectResponse(
            url="/admin/groups", status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        flash_message(request, f"Error creating group: {str(e)}", "danger")
        return RedirectResponse(
            url="/admin/groups/new", status_code=status.HTTP_303_SEE_OTHER
        )


@app.get("/admin/groups/{group_id}", response_class=HTMLResponse)
async def admin_edit_group(
    request: Request,
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Admin edit group page
    """
    group = await get_group(db, group_id)

    if not group:
        flash_message(request, "Group not found", "danger")
        return RedirectResponse(
            url="/admin/groups", status_code=status.HTTP_303_SEE_OTHER
        )

    return templates.TemplateResponse(
        "admin/group_form.html",
        {
            "request": request,
            "user": user,
            "group": group,
            "messages": get_flash_messages(request),
        },
    )


@app.post("/admin/groups/{group_id}", response_class=HTMLResponse)
async def admin_update_group(
    request: Request,
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    active: bool = Form(False),
    backfill: bool = Form(False),
    min_files: int = Form(1),
    min_size: int = Form(0),
    backfill_target: Optional[int] = Form(None),
):
    """
    Admin update group
    """
    group = await get_group(db, group_id)

    if not group:
        flash_message(request, "Group not found", "danger")
        return RedirectResponse(
            url="/admin/groups", status_code=status.HTTP_303_SEE_OTHER
        )

    group_in = GroupUpdate(
        name=name,
        description=description,
        active=active,
        backfill=backfill,
        min_files=min_files,
        min_size=min_size,
    )

    if backfill_target is not None:
        group_in.backfill_target = backfill_target

    try:
        updated_group = await update_group(db, group_id, group_in)
        flash_message(
            request, f"Group '{updated_group.name}' updated successfully", "success"
        )
        return RedirectResponse(
            url="/admin/groups", status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        flash_message(request, f"Error updating group: {str(e)}", "danger")
        return RedirectResponse(
            url=f"/admin/groups/{group_id}", status_code=status.HTTP_303_SEE_OTHER
        )


@app.post("/admin/groups/{group_id}/delete", response_class=HTMLResponse)
async def admin_delete_group(
    request: Request,
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Admin delete group
    """
    group = await get_group(db, group_id)

    if not group:
        flash_message(request, "Group not found", "danger")
        return RedirectResponse(
            url="/admin/groups", status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        group_name = group.name
        await delete_group(db, group_id)
        flash_message(request, f"Group '{group_name}' deleted successfully", "success")
    except Exception as e:
        flash_message(request, f"Error deleting group: {str(e)}", "danger")

    return RedirectResponse(url="/admin/groups", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Admin settings page
    """
    # Get application settings
    settings = await get_app_settings(db)

    return templates.TemplateResponse(
        "admin/settings.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "messages": get_flash_messages(request),
        },
    )


@app.post("/admin/settings", response_class=HTMLResponse)
async def admin_update_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Admin update settings
    """
    # Get form data
    form_data = await request.form()

    # Create AppSettings object
    app_settings = AppSettings(
        allow_registration=form_data.get("allow_registration") == "on",
        nntp_server=form_data.get("nntp_server", ""),
        nntp_port=int(form_data.get("nntp_port", 119)),
        nntp_ssl=form_data.get("nntp_ssl") == "on",
        nntp_ssl_port=int(form_data.get("nntp_ssl_port", 563)),
        nntp_username=form_data.get("nntp_username", ""),
        nntp_password=form_data.get("nntp_password", ""),
        update_threads=int(form_data.get("update_threads", 1)),
        releases_threads=int(form_data.get("releases_threads", 1)),
        postprocess_threads=int(form_data.get("postprocess_threads", 1)),
        backfill_days=int(form_data.get("backfill_days", 3)),
        retention_days=int(form_data.get("retention_days", 1100)),
    )

    # Update settings
    try:
        await update_app_settings(db, app_settings)
        flash_message(request, "Settings updated successfully", "success")
    except Exception as e:
        flash_message(request, f"Error updating settings: {str(e)}", "danger")

    return RedirectResponse(
        url="/admin/settings", status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    User profile page
    """
    user = await get_current_web_user(request, db)
    if not user:
        flash_message(request, "Please login to access this page", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": user,
            "messages": get_flash_messages(request),
        },
    )


@app.post("/profile", response_class=HTMLResponse)
async def profile_update(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Update user profile
    """
    user = await get_current_web_user(request, db)
    if not user:
        flash_message(request, "Please login to access this page", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Get form data
    form_data = await request.form()

    # Create UserUpdate object
    user_update = UserUpdate(
        first_name=form_data.get("first_name"),
        last_name=form_data.get("last_name"),
        email=form_data.get("email"),
    )

    # Update password if provided
    current_password = form_data.get("current_password")
    new_password = form_data.get("new_password")
    confirm_password = form_data.get("confirm_password")

    if current_password and new_password and confirm_password:
        from app.core.security import verify_password

        # Check if current password is correct
        if not verify_password(current_password, user.hashed_password):
            flash_message(request, "Current password is incorrect", "danger")
            return RedirectResponse(
                url="/profile", status_code=status.HTTP_303_SEE_OTHER
            )

        # Check if new passwords match
        if new_password != confirm_password:
            flash_message(request, "New passwords do not match", "danger")
            return RedirectResponse(
                url="/profile", status_code=status.HTTP_303_SEE_OTHER
            )

        # Update password
        user_update.password = new_password

    # Update user
    try:
        await update_user(db, user.id, user_update)
        flash_message(request, "Profile updated successfully", "success")
    except Exception as e:
        flash_message(request, f"Error updating profile: {str(e)}", "danger")

    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "ok", "version": "0.5.4"}


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """
    Startup event handler
    """
    # Start background tasks
    start_background_tasks()


@app.on_event("shutdown")
async def shutdown_event():
    """
    Shutdown event handler
    """
    # Stop background tasks
    stop_background_tasks()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
