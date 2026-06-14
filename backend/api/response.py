from typing import Any, Optional


def success_response(data: Any = None, message: Optional[str] = None) -> dict:
    response = {"status": "success"}
    if data is not None:
        response["data"] = data
    if message is not None:
        response["message"] = message
    return response


def error_response(detail: str, code: int = 400) -> dict:
    return {"status": "error", "detail": detail, "code": code}


def paginated_response(items: list, total: int, limit: int, offset: int) -> dict:
    return {
        "status": "success",
        "data": items,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        },
    }
