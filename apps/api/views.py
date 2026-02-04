"""REST API views."""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.vagt.models import Controller, StatusLog


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request: Request) -> Response:
    """Health check endpoint."""
    return Response({"status": "healthy", "service": "watchtower"})


class ControllerListView(APIView):
    """GET /api/v1/controllers/ - List all controllers."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        controllers = Controller.objects.filter(is_active=True).order_by("number")
        data = [
            {
                "id": c.id,
                "number": c.number,
                "name": c.name,
                "employee_id": c.employee_id,
                "status": c.status,
                "status_display": c.get_status_display(),
            }
            for c in controllers
        ]
        return Response({"count": len(data), "results": data})


class StatusLogListView(APIView):
    """GET /api/v1/logs/ - List recent status changes."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        limit = min(int(request.query_params.get("limit", 50)), 200)
        logs = StatusLog.objects.select_related("controller", "changed_by")[:limit]
        data = [
            {
                "id": log.id,
                "controller": str(log.controller),
                "old_status": log.old_status,
                "new_status": log.new_status,
                "changed_by": log.changed_by.username if log.changed_by else None,
                "changed_at": log.changed_at.isoformat(),
            }
            for log in logs
        ]
        return Response({"count": len(data), "results": data})
