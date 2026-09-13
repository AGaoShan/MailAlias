from .accounts import router as accounts_router
from .aliases import router as aliases_router
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .mappings import router as mappings_router
from .pickup import router as pickup_router

__all__ = [
    "accounts_router",
    "aliases_router",
    "auth_router",
    "dashboard_router",
    "mappings_router",
    "pickup_router",
]
