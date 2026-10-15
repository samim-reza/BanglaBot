"""Platform admin: login from settings, accounts CRUD, cross-account views, sales inquiries.

One combined ``router`` (prefix ``/api/admin``, tag ``admin``) assembled from:
``overview`` (login, form choices, counters), ``merchants`` (accounts CRUD),
``addons`` (add-on set + owners' requests), ``impersonation``, ``records``
(records / calls / recordings) and ``inquiries``; shared helpers in ``common``.
"""

from fastapi import APIRouter

from app.api.routes.admin import addons, impersonation, inquiries, merchants, overview, records
from app.api.routes.admin.addons import AddonDecision, AddonsUpdate
from app.api.routes.admin.common import admin_out
from app.api.routes.admin.inquiries import SalesInquiryUpdate

router = APIRouter(prefix="/api/admin", tags=["admin"])
for _module in (overview, merchants, addons, impersonation, records, inquiries):
    router.include_router(_module.router)

__all__ = ["AddonDecision", "AddonsUpdate", "SalesInquiryUpdate", "admin_out", "router"]
