from contextlib import asynccontextmanager

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Set up logging first
from app.core.logging import setup_logging

setup_logging()

import logging

logger = logging.getLogger(__name__)
logger.info("Starting NZB Indexer application")

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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    start_background_tasks()
    yield
    # Shutdown
    await stop_background_tasks()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Modern Usenet Indexer with FastAPI",
    version="0.9.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
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

# Add built-in functions to template environment
templates.env.globals["max"] = max
templates.env.globals["min"] = min

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
async def browse(
    request: Request,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    group_id: Optional[int] = None,
    page: int = 1,
    sort_by: str = "added_date",
    sort_desc: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """
    Browse page
    """
    user = await get_current_web_user(request, db)

    # Get releases with pagination
    per_page = 20
    skip = (page - 1) * per_page

    # Import release service
    from app.services.release import get_releases

    # Get releases
    releases_data = await get_releases(
        db,
        skip=skip,
        limit=per_page,
        search=search,
        category_id=category_id,
        group_id=group_id,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    # Get categories organized by parent/child relationship
    from app.db.models.category import Category
    from app.db.models.release import Release
    from sqlalchemy import and_, func, or_, select

    # Get all categories
    query = (
        select(Category, func.count(Release.id).label("release_count"))
        .outerjoin(
            Release, and_(Release.category_id == Category.id, Release.status == 1)
        )
        .filter(Category.active == True)
        .group_by(Category.id)
        .order_by(Category.sort_order)
    )
    result = await db.execute(query)
    categories_with_counts = result.all()

    # Organize categories into main categories and subcategories
    main_categories = []
    subcategories = {}
    current_category = None

    for cat, release_count in categories_with_counts:
        cat.release_count = release_count  # Add release count to category object

        if cat.parent_id is None:
            # This is a main category
            main_categories.append(cat)
            subcategories[cat.id] = []
        else:
            # This is a subcategory
            if cat.parent_id in subcategories:
                subcategories[cat.parent_id].append(cat)

        # Check if this is the currently selected category
        if category_id and cat.id == category_id:
            current_category = cat

    # Add helper function to check if a main category has an active subcategory
    def has_active_subcategory(main_cat_id, active_cat_id):
        if not active_cat_id:
            return False
        for subcat in subcategories.get(main_cat_id, []):
            if subcat.id == active_cat_id:
                return True
        return False

    # Add the helper function to the template context
    templates.env.globals["has_active_subcategory"] = has_active_subcategory

    # Create pagination object
    total = releases_data["total"]
    releases = releases_data["items"]

    # Build pagination URLs with all parameters
    def build_url(page_num):
        """Build URL for a specific page"""
        params = {"page": page_num}
        if search:
            params["search"] = search
        if category_id:
            params["category_id"] = category_id
        if group_id:
            params["group_id"] = group_id
        if sort_by:
            params["sort_by"] = sort_by
        if sort_desc:
            params["sort_desc"] = sort_desc

        url = "/browse?" + "&".join([f"{k}={v}" for k, v in params.items()])
        return url

    def iter_pages(left_edge=2, left_current=2, right_current=3, right_edge=2):
        """
        Generate page numbers for pagination with smart truncation
        Returns None for gaps where ellipsis should be shown
        """
        last = (total + per_page - 1) // per_page

        # If there are few enough pages, just show them all
        if last <= (left_edge + left_current + right_current + right_edge + 2):
            yield from range(1, last + 1)
            return

        # Calculate which pages to show
        left_range = range(1, left_edge + 1)
        right_range = range(last - right_edge + 1, last + 1)
        current_left_range = range(max(1, page - left_current), page + 1)
        current_right_range = range(page + 1, min(last, page + right_current) + 1)

        # Combine ranges and sort
        pages_to_show = (
            set(left_range)
            | set(right_range)
            | set(current_left_range)
            | set(current_right_range)
        )
        pages_list = sorted(pages_to_show)

        # Yield pages with None for gaps
        prev_page = 0
        for page_num in pages_list:
            if page_num - prev_page > 1:
                yield None  # Gap for ellipsis
            yield page_num
            prev_page = page_num

    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
        "has_prev": page > 1,
        "has_next": page < ((total + per_page - 1) // per_page),
        "prev_url": build_url(page - 1) if page > 1 else None,
        "next_url": (
            build_url(page + 1) if page < ((total + per_page - 1) // per_page) else None
        ),
        "iter_pages": iter_pages,
        "url_for_page": build_url,
    }

    # Get user downloads if user is logged in
    user_downloads = []
    if user:
        # TODO: Implement user downloads
        pass

    return templates.TemplateResponse(
        "browse.html",
        {
            "request": request,
            "user": user,
            "releases": releases,
            "main_categories": main_categories,
            "subcategories": subcategories,
            "current_category": current_category,
            "search": search,
            "category_id": category_id,
            "group_id": group_id,
            "sort_by": sort_by,
            "sort_desc": sort_desc,
            "pagination": pagination,
            "user_downloads": user_downloads,
            "messages": get_flash_messages(request),
        },
    )


@app.get("/releases/{release_id}", response_class=HTMLResponse)
async def release_detail(
    request: Request, release_id: int, db: AsyncSession = Depends(get_db)
):
    """
    Release detail page
    """
    user = await get_current_web_user(request, db)

    # Get release
    from app.services.release import get_release

    release = await get_release(db, release_id)

    if not release:
        flash_message(request, "Release not found", "danger")
        return RedirectResponse(url="/browse", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "release_detail.html",
        {
            "request": request,
            "user": user,
            "release": release,
            "messages": get_flash_messages(request),
        },
    )


@app.get("/releases/{release_id}/download")
async def download_release(
    request: Request, release_id: int, db: AsyncSession = Depends(get_db)
):
    """
    Download NZB file for a release
    """
    user = await get_current_web_user(request, db)

    if not user:
        flash_message(request, "Please login to download NZB files", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Get release
    from app.services.release import get_release

    release = await get_release(db, release_id)

    if not release:
        flash_message(request, "Release not found", "danger")
        return RedirectResponse(url="/browse", status_code=status.HTTP_303_SEE_OTHER)

    # Get NZB file
    from app.services.nzb import get_nzb_for_release

    nzb_path = await get_nzb_for_release(db, release_id)

    if not nzb_path:
        flash_message(request, "NZB file not found", "danger")
        return RedirectResponse(url="/browse", status_code=status.HTTP_303_SEE_OTHER)

    # Increment grab count
    # TODO: Implement increment_grab_count
    # await increment_grab_count(db, release_id, user.id)

    # Return NZB file
    filename = f"{release.name.replace(' ', '_')}.nzb"
    return FileResponse(
        path=nzb_path, filename=filename, media_type="application/x-nzb"
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
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Login attempt for user: {login}")

    from app.core.security import verify_password
    from app.services.user import get_user_by_username

    # Try to find user by email first
    user = await get_user_by_email(db, email=login)
    if user:
        logger.info(f"User found by email: {user.username}")

    # If not found by email, try by username
    if not user:
        user = await get_user_by_username(db, username=login)
        if user:
            logger.info(f"User found by username: {user.username}")

    if not user:
        logger.warning(f"Login failed: User not found for login: {login}")
        flash_message(request, "Invalid username/email or password", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if not verify_password(password, user.hashed_password):
        logger.warning(f"Login failed: Invalid password for user: {user.username}")
        flash_message(request, "Invalid username/email or password", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if not user.is_active:
        logger.warning(f"Login failed: User is inactive: {user.username}")
        flash_message(request, "Your account is inactive", "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    if remember:
        access_token_expires = timedelta(days=30)  # Longer expiration for "remember me"
        logger.info(f"Remember me enabled for user: {user.username}")

    access_token = create_access_token(user.id, expires_delta=access_token_expires)
    request.session["access_token"] = access_token
    logger.info(f"Access token created and stored in session for user: {user.username}")

    # Update last login time
    user.last_login = datetime.now(timezone.utc)
    db.add(user)
    await db.commit()
    logger.info(f"Last login time updated for user: {user.username}")

    # Check if session contains the access token
    session_token = request.session.get("access_token")
    if session_token:
        logger.info(f"Session contains access token for user: {user.username}")
    else:
        logger.warning(
            f"Session does not contain access token for user: {user.username}"
        )

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


@app.get("/admin/categories", response_class=HTMLResponse)
async def admin_categories(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Admin categories management page
    """
    # Get categories
    from app.services.category import get_categories

    categories = await get_categories(db)

    return templates.TemplateResponse(
        "admin/categories.html",
        {
            "request": request,
            "user": user,
            "categories": categories,
            "messages": get_flash_messages(request),
        },
    )


@app.get("/admin/groups", response_class=HTMLResponse)
async def admin_groups(
    request: Request,
    active_page: int = 1,
    inactive_page: int = 1,
    backfill_page: int = 1,
    active_search: Optional[str] = None,
    inactive_search: Optional[str] = None,
    backfill_search: Optional[str] = None,
    discover_pattern: Optional[str] = None,
    tab: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Admin groups management page
    """
    # Set pagination parameters
    per_page = 10

    # Get active groups with pagination and search
    active_skip = (active_page - 1) * per_page
    active_groups_data = await get_groups(
        db, skip=active_skip, limit=per_page, active=True, search=active_search
    )

    # Create pagination object for active groups
    active_groups = {
        "items": active_groups_data["items"],
        "total": active_groups_data["total"],
        "per_page": per_page,
        "pages": (active_groups_data["total"] + per_page - 1) // per_page,
    }

    # Get inactive groups with pagination and search
    inactive_skip = (inactive_page - 1) * per_page
    inactive_groups_data = await get_groups(
        db, skip=inactive_skip, limit=per_page, active=False, search=inactive_search
    )

    # Create pagination object for inactive groups
    inactive_groups = {
        "items": inactive_groups_data["items"],
        "total": inactive_groups_data["total"],
        "per_page": per_page,
        "pages": (inactive_groups_data["total"] + per_page - 1) // per_page,
    }

    # Get backfill groups with pagination and search
    backfill_skip = (backfill_page - 1) * per_page
    backfill_groups_data = await get_groups(
        db, skip=backfill_skip, limit=per_page, backfill=True, search=backfill_search
    )

    # Create pagination object for backfill groups
    backfill_groups = {
        "items": backfill_groups_data["items"],
        "total": backfill_groups_data["total"],
        "per_page": per_page,
        "pages": (backfill_groups_data["total"] + per_page - 1) // per_page,
    }

    # Get global discovery status
    global discovery_running

    return templates.TemplateResponse(
        "admin/groups.html",
        {
            "request": request,
            "user": user,
            "active_groups": active_groups,
            "inactive_groups": inactive_groups,
            "backfill_groups": backfill_groups,
            "active_page": active_page,
            "inactive_page": inactive_page,
            "backfill_page": backfill_page,
            "active_search": active_search,
            "inactive_search": inactive_search,
            "backfill_search": backfill_search,
            "discover_pattern": discover_pattern if discover_pattern else "*",
            "tab": tab,
            "discovery_running": discovery_running,
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


# This route was duplicated - removed the second instance


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
    backfill_days: int = Form(0),
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
        backfill_days=backfill_days,
    )

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


# Global variable to track if discovery is running and should be cancelled
discovery_running = False
discovery_cancel = False


@app.get("/admin/cancel-discovery")
async def admin_cancel_discovery(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Cancel the current discovery job
    """
    global discovery_cancel
    discovery_cancel = True

    flash_message(
        request,
        "Discovery job cancellation requested. The job will stop after the current batch completes.",
        "warning",
    )
    return RedirectResponse(url="/admin/groups", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/discover-groups")
async def admin_discover_groups(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
    pattern: str = Form("*"),
    active: bool = Form(False),
    batch_size: int = Form(100),
):
    """
    Discover newsgroups from NNTP server and add them to the database
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(
            f"Form data received: pattern={pattern}, active={active}, batch_size={batch_size}"
        )

        # Check if discovery is already running
        global discovery_running
        if discovery_running:
            flash_message(
                request,
                "Discovery is already running. Please wait for it to complete or cancel it.",
                "warning",
            )
            return RedirectResponse(
                url="/admin/groups", status_code=status.HTTP_303_SEE_OTHER
            )

        # Discover newsgroups
        from app.services.nntp import discover_newsgroups

        logger.info(f"Discovering newsgroups with pattern: {pattern}, active: {active}")
        stats = await discover_newsgroups(
            db, pattern=pattern, active=active, batch_size=batch_size
        )
        logger.info(f"Discovery complete: {stats}")

        # Flash success message with stats
        if stats.get("cancelled", False):
            flash_message(
                request,
                f"Discovery cancelled! Processed {stats['processed']} of {stats['total']} groups. Added {stats['added']}, updated {stats['updated']}, failed {stats['failed']}.",
                "warning",
            )
        else:
            flash_message(
                request,
                f"Discovery complete! Found {stats['total']} groups, added {stats['added']}, updated {stats['updated']}, skipped {stats['skipped']}, failed {stats['failed']}",
                "success",
            )

    except ValueError as e:
        logger.error(f"Value error in discover_groups: {str(e)}")
        flash_message(request, f"Error: {str(e)}", "danger")
    except Exception as e:
        import traceback

        logger.error(f"Error in discover_groups: {str(e)}")
        logger.error(traceback.format_exc())
        flash_message(request, f"Error: {str(e)}", "danger")

    # Redirect back to the groups page
    return RedirectResponse(url="/admin/groups", status_code=status.HTTP_303_SEE_OTHER)


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


@app.post("/admin/test-nntp-connection")
async def admin_test_nntp_connection(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(admin_required),
):
    """
    Test NNTP connection with provided settings
    """
    # Get request body
    data = await request.json()

    try:
        # Create NNTP service with provided settings
        from app.services.nntp import NNTPService

        nntp_service = NNTPService(
            server=data.get("server"),
            port=data.get("port") if not data.get("ssl") else data.get("ssl_port"),
            use_ssl=data.get("ssl"),
            username=data.get("username"),
            password=data.get("password"),
        )

        # Test connection
        conn = nntp_service.connect()

        # Get server info
        welcome = conn.welcome

        # Close connection
        conn.quit()

        return {
            "status": "success",
            "message": "Connection successful",
            "welcome": welcome.decode() if isinstance(welcome, bytes) else welcome,
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"Connection failed: {str(e)}"},
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


@app.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    API keys management page
    """
    user = await get_current_web_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "api_keys.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
        },
    )


@app.post("/api-keys/generate")
async def generate_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a new API key for the user
    """
    user = await get_current_web_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Generate a random API key
    import secrets

    api_key = secrets.token_urlsafe(24)

    # Update user with new API key
    user.api_key = api_key
    db.add(user)
    await db.commit()

    flash_message(request, "API key generated successfully", "success")
    return RedirectResponse(url="/api-keys", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/api-keys/regenerate")
async def regenerate_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate API key for the user
    """
    user = await get_current_web_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Generate a new random API key
    import secrets

    api_key = secrets.token_urlsafe(24)

    # Update user with new API key
    user.api_key = api_key
    db.add(user)
    await db.commit()

    flash_message(request, "API key regenerated successfully", "success")
    return RedirectResponse(url="/api-keys", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "ok", "version": "0.9.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
