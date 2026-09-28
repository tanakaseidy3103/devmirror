"""
DevMirror - API v1 ルーター
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    dashboard,
    demo,
    fingerprints,
    diffs,
    incidents,
    projects,
    scanner,
    vm,
    vm_console,
)

api_router = APIRouter()

api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(scanner.router, prefix="/scanner", tags=["Scanner"])
api_router.include_router(fingerprints.router, prefix="/fingerprints", tags=["Fingerprints"])
api_router.include_router(diffs.router, prefix="/diffs", tags=["Diffs"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["Incidents"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(demo.router, prefix="/demo", tags=["Demo"])
api_router.include_router(vm.router, prefix="/vm", tags=["VM"])
api_router.include_router(vm_console.router, prefix="/vm", tags=["VM Console"])
