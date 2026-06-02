"""Streamlit session_state — sohbet geçmişi ve oturum yönetimi."""

from __future__ import annotations

from typing import Any

import streamlit as st

Message = dict[str, Any]

DEFAULT_SUGGESTIONS: list[str] = [
    "Kayıt dondurma şartları nelerdir?",
    "Mazeret sınavına kimler başvurabilir?",
    "Mezuniyet için gerekli şartlar nelerdir?",
    "Ders kaydı süreci nasıl işler?",
]


def init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "active_session_id" not in st.session_state:
        st.session_state.active_session_id = None
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = []
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None
    if "flash_message" not in st.session_state:
        st.session_state.flash_message = None
    if "app_page" not in st.session_state:
        st.session_state.app_page = "chat"
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False


def reset_chat(*, clear_session_id: bool = True) -> None:
    st.session_state.messages = []
    st.session_state.pending_question = None
    if clear_session_id:
        st.session_state.active_session_id = None


def set_active_session(session_id: str | None) -> None:
    st.session_state.active_session_id = session_id


def load_messages_from_api(api_messages: list[dict]) -> None:
    """Backend mesaj listesini UI formatına çevirir."""
    st.session_state.messages = []
    for msg in api_messages:
        role = msg.get("role", "assistant")
        entry: Message = {
            "role": role,
            "content": msg.get("content", ""),
        }
        if role == "assistant":
            entry["citations"] = []
            entry["validation_warning"] = None
            entry["retrieval_debug"] = None
            entry["message_id"] = str(msg.get("id", ""))
        st.session_state.messages.append(entry)


def append_user_message(content: str) -> None:
    st.session_state.messages.append({"role": "user", "content": content.strip()})


def append_assistant_message(
    *,
    content: str,
    citations: list[dict] | None = None,
    validation_warning: str | None = None,
    retrieval_debug: dict | None = None,
    agent_steps: list[str] | None = None,
    message_id: str | None = None,
) -> None:
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": content,
            "citations": citations or [],
            "validation_warning": validation_warning,
            "retrieval_debug": retrieval_debug,
            "agent_steps": agent_steps or [],
            "message_id": message_id,
        }
    )


def has_messages() -> bool:
    return bool(st.session_state.get("messages"))
