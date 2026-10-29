import time
from typing import Any
import httpx


def handle_http_request(payload: dict[str, Any]) -> dict[str, Any]:
    url = payload["url"]
    method = payload.get("method", "GET").upper()
    headers = payload.get("headers", {})
    body = payload.get("body")
    params = payload.get("params")
    timeout = float(payload.get("timeout", 10.0))

    with httpx.Client(timeout=timeout) as client:
        req_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "params": params,
        }
        if body is not None:
            if isinstance(body, dict):
                req_kwargs["json"] = body
            else:
                req_kwargs["content"] = str(body)

        response = client.request(**req_kwargs)
        try:
            resp_data = response.json()
        except Exception:
            resp_data = response.text

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "response": resp_data,
        }


def handle_data_processing(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "sum").lower()
    data = payload.get("data", [])

    if action == "sum":
        total = sum(data)
        return {"action": "sum", "count": len(data), "result": total}
    elif action == "average":
        if not data:
            return {"action": "average", "count": 0, "result": 0}
        avg = sum(data) / len(data)
        return {"action": "average", "count": len(data), "result": avg}
    elif action == "word_count":
        text = str(payload.get("text", ""))
        words = [w for w in text.split() if w]
        return {"action": "word_count", "word_count": len(words), "char_count": len(text)}
    elif action == "sort":
        reverse = bool(payload.get("reverse", False))
        sorted_list = sorted(data, reverse=reverse)
        return {"action": "sort", "count": len(data), "result": sorted_list}
    else:
        raise ValueError(f"Unsupported data_processing action: '{action}'")


def handle_notification(payload: dict[str, Any]) -> dict[str, Any]:
    recipient = payload.get("recipient", "user@example.com")
    channel = payload.get("channel", "email")
    message = payload.get("message", "")
    return {
        "channel": channel,
        "recipient": recipient,
        "status": "delivered",
        "message_length": len(message),
    }


def handle_sleep(payload: dict[str, Any]) -> dict[str, Any]:
    seconds = min(max(float(payload.get("seconds", 1.0)), 0.0), 10.0)
    time.sleep(seconds)
    return {"slept_seconds": seconds}


def dispatch_job_handler(job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    handlers = {
        "http_request": handle_http_request,
        "data_processing": handle_data_processing,
        "notification": handle_notification,
        "sleep": handle_sleep,
    }
    handler = handlers.get(job_type)
    if not handler:
        raise ValueError(f"Unknown job_type: '{job_type}'")
    return handler(payload)
