"""
Medeniyet Üniversitesi AI Asistanı — Streamlit arayüzü.
Sohbet ve Yönetim Paneli (akademik bitirme projesi; resmi üniversite uygulaması değildir).
"""

import streamlit as st

from admin_view import render_admin_page
from api_client import (
    ApiClientError,
    DELETE_SESSION_ERROR,
    create_chat_session,
    delete_chat_session,
    get_session_messages,
    list_chat_sessions,
    post_chat,
)
from components import (
    USER_ERROR_MESSAGE,
    apply_custom_styles,
    render_assistant_message,
    render_chat_history,
    render_header,
    render_page_nav,
    render_sidebar,
    render_suggestion_cards,
)
from session import (
    append_assistant_message,
    append_user_message,
    init_session_state,
    load_messages_from_api,
    reset_chat,
    set_active_session,
)

CHAT_PLACEHOLDER = (
    "Yönetmelik, sınav, kayıt, belge veya akademik süreçlerle ilgili sorunuzu yazın..."
)


st.set_page_config(
    page_title="Medeniyet Üniversitesi AI Asistanı",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_styles()
init_session_state()


def _set_app_page(page: str) -> None:
    st.session_state.app_page = page
    st.rerun()


render_page_nav(on_select_page=_set_app_page)

if st.session_state.get("app_page", "chat") == "admin":
    render_admin_page()
    st.stop()


def refresh_session_list() -> None:
    try:
        st.session_state.chat_sessions = list_chat_sessions()
    except ApiClientError:
        pass


def _handle_new_chat() -> None:
    try:
        session = create_chat_session(title="Yeni Sohbet")
        reset_chat(clear_session_id=False)
        set_active_session(session.get("id"))
        refresh_session_list()
    except ApiClientError:
        reset_chat()
    st.rerun()


def _handle_delete_session(session_id: str) -> None:
    active = str(st.session_state.get("active_session_id") or "")
    try:
        delete_chat_session(session_id)
        if active == session_id:
            reset_chat()
        refresh_session_list()
        st.session_state.flash_message = ("success", "Sohbet silindi.")
    except ApiClientError:
        st.session_state.flash_message = ("error", DELETE_SESSION_ERROR)
    st.rerun()


def _handle_load_session(session_id: str) -> None:
    try:
        messages = get_session_messages(session_id)
        load_messages_from_api(messages)
        set_active_session(session_id)
    except ApiClientError:
        st.error(USER_ERROR_MESSAGE)
    st.rerun()


def _queue_question(question: str) -> None:
    st.session_state.pending_question = question.strip()
    st.rerun()


def send_question(question: str) -> None:
    trimmed = (question or "").strip()
    if not trimmed:
        return

    append_user_message(trimmed)

    with st.chat_message("user", avatar="✍"):
        st.markdown(trimmed)

    with st.chat_message("assistant", avatar="🤖"):
        try:
            with st.spinner("Cevap hazırlanıyor..."):
                response = post_chat(trimmed, session_id=st.session_state.active_session_id)

            if response.get("session_id"):
                set_active_session(response["session_id"])

            citations = response.get("citations") or []
            answer = response.get("answer", "")

            agent_steps = response.get("agent_steps") or response.get("steps") or []
            msg = {
                "role": "assistant",
                "content": answer,
                "citations": citations,
                "validation_warning": response.get("validation_warning"),
                "retrieval_debug": response.get("retrieval_debug"),
                "agent_steps": agent_steps,
                "message_id": response.get("assistant_message_id"),
            }
            append_assistant_message(
                content=answer,
                citations=citations,
                validation_warning=response.get("validation_warning"),
                retrieval_debug=response.get("retrieval_debug"),
                agent_steps=agent_steps,
                message_id=response.get("assistant_message_id"),
            )
            render_assistant_message(msg)
            refresh_session_list()
        except ApiClientError:
            st.error(USER_ERROR_MESSAGE)
            append_assistant_message(content=USER_ERROR_MESSAGE, citations=[])
        except Exception:
            st.error(USER_ERROR_MESSAGE)
            append_assistant_message(content=USER_ERROR_MESSAGE, citations=[])


refresh_session_list()

if st.session_state.get("flash_message"):
    kind, text = st.session_state.flash_message
    st.session_state.flash_message = None
    icon = "✅" if kind == "success" else "⚠️"
    st.toast(text, icon=icon)

render_sidebar(
    on_new_chat=_handle_new_chat,
    on_load_session=_handle_load_session,
    on_delete_session=_handle_delete_session,
)
render_header()
render_suggestion_cards(on_select=_queue_question)
render_chat_history()

if st.session_state.get("pending_question"):
    q = st.session_state.pending_question
    st.session_state.pending_question = None
    send_question(q)

if prompt := st.chat_input(CHAT_PLACEHOLDER, key="chat_input"):
    send_question(prompt)
