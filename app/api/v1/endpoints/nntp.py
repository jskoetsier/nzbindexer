from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.db.models.user import User
from app.db.session import get_db
from app.services.nntp import NNTPService

router = APIRouter()


class NNTPConnectionTest(BaseModel):
    """
    Schema for NNTP connection test
    """
    server: str
    port: int
    ssl: bool = False
    ssl_port: int = 563
    username: str = ""
    password: str = ""


@router.post("/test-connection", status_code=status.HTTP_200_OK)
async def test_nntp_connection(
    connection: NNTPConnectionTest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Test NNTP connection with provided settings
    """
    try:
        # Create NNTP service with provided settings
        nntp_service = NNTPService(
            server=connection.server,
            port=connection.port if not connection.ssl else connection.ssl_port,
            use_ssl=connection.ssl,
            username=connection.username,
            password=connection.password,
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connection failed: {str(e)}",
        )
