import os

import httpx

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
TIMEOUT_SECONDS = 60.0

USER_FACING_ERROR = "Cevap alınırken bir sorun oluştu. Lütfen tekrar deneyin."
DELETE_SESSION_ERROR = "Sohbet silinirken bir sorun oluştu."


class ApiClientError(Exception):
    """Backend isteği başarısız olduğunda kullanıcıya gösterilecek hata."""

    def __init__(self, message: str, *, technical: str | None = None) -> None:
        self.message = message
        self.technical = technical or message
        super().__init__(message)


def get_backend_url() -> str:
    return os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL).rstrip("/")


def _request(method: str, path: str, **kwargs) -> dict | list:
    url = f"{get_backend_url()}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise ApiClientError(USER_FACING_ERROR, technical=str(exc)) from exc
    except httpx.TimeoutException as exc:
        raise ApiClientError(USER_FACING_ERROR, technical=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise ApiClientError(
            USER_FACING_ERROR,
            technical=f"HTTP {exc.response.status_code}",
        ) from exc


def fetch_health() -> dict:
    return _request("GET", "/health")


def create_chat_session(title: str = "Yeni Sohbet") -> dict:
    return _request("POST", "/chat/sessions", json={"title": title})


def list_chat_sessions() -> list[dict]:
    data = _request("GET", "/chat/sessions")
    return data.get("sessions", [])


def delete_chat_session(session_id: str) -> dict:
    url = f"{get_backend_url()}/chat/sessions/{session_id}"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.delete(url)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise ApiClientError(
            DELETE_SESSION_ERROR,
            technical=f"HTTP {exc.response.status_code}",
        ) from exc
    except httpx.ConnectError as exc:
        raise ApiClientError(DELETE_SESSION_ERROR, technical=str(exc)) from exc
    except httpx.TimeoutException as exc:
        raise ApiClientError(DELETE_SESSION_ERROR, technical=str(exc)) from exc


def get_session_messages(session_id: str) -> list[dict]:
    data = _request("GET", f"/chat/sessions/{session_id}/messages")
    return data.get("messages", [])


def post_chat(question: str, session_id: str | None = None) -> dict:
    payload: dict = {"question": question.strip()}
    if session_id:
        payload["session_id"] = session_id
    return _request("POST", "/chat", json=payload)


def submit_feedback(
    *,
    rating: str,
    message_id: str | None = None,
    comment: str | None = None,
) -> dict:
    payload: dict = {"rating": rating}
    if message_id:
        payload["message_id"] = message_id
    if comment:
        payload["comment"] = comment
    return _request("POST", "/feedback", json=payload)
