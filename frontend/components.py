"""Streamlit UI bileşenleri — header, sidebar, chat, kaynaklar."""

from __future__ import annotations

import streamlit as st

from session import DEFAULT_SUGGESTIONS, Message, has_messages

SOURCES_MARKER = "\n\nKaynaklar:"

USER_ERROR_MESSAGE = "Cevap alınırken bir sorun oluştu. Lütfen tekrar deneyin."


def apply_custom_styles() -> None:
    from ui_styles import CUSTOM_CSS

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def strip_inline_sources(answer: str) -> str:
    if SOURCES_MARKER in answer:
        return answer.split(SOURCES_MARKER, maxsplit=1)[0].strip()
    return answer.strip()


def render_page_nav(*, on_select_page) -> None:
    """Sohbet ↔ Yönetim Paneli geçişi (sidebar üst)."""
    with st.sidebar:
        st.markdown("##### Görünüm")
        page = st.radio(
            "Sayfa",
            options=["chat", "admin"],
            format_func=lambda p: "Sohbet" if p == "chat" else "Yönetim Paneli",
            key="nav_page_radio",
            index=0 if st.session_state.get("app_page", "chat") == "chat" else 1,
            label_visibility="collapsed",
        )
        if page != st.session_state.get("app_page"):
            on_select_page(page)


def render_sidebar(*, on_new_chat, on_load_session, on_delete_session) -> None:
    with st.sidebar:
        st.markdown(
            '<p class="sidebar-brand">Üniversite AI Asistanı</p>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="new-chat-btn">', unsafe_allow_html=True)
        if st.button("+ Yeni Sohbet", use_container_width=True, key="btn_new_chat"):
            on_new_chat()
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("##### Sohbetler")
        sessions = st.session_state.get("chat_sessions") or []
        if not sessions:
            st.caption("Henüz kayıtlı sohbet yok.")
        else:
            for i, session in enumerate(sessions):
                sid = str(session.get("id", ""))
                title = session.get("title", "Sohbet")[:100]
                is_active = sid == str(st.session_state.get("active_session_id") or "")
                label = f"{'• ' if is_active else ''}{title}"
                col_open, col_del = st.columns([3.5, 1], gap="small")
                with col_open:
                    if st.button(
                        label,
                        key=f"session_{i}_{sid[:8]}",
                        use_container_width=True,
                    ):
                        on_load_session(sid)
                with col_del:
                    if st.button(
                        "🗑",
                        key=f"delete_session_{sid}",
                        help="Sohbeti sil",
                    ):
                        on_delete_session(sid)

        st.markdown(
            '<p class="sidebar-footer">Ardacan Altundaşar</p>',
            unsafe_allow_html=True,
        )


def render_header() -> None:
    """Boş ekranda ana alan başlığı (ChatGPT/Gemini karşılama)."""
    if has_messages():
        st.markdown(
            '<p class="hero-title" style="font-size:1.25rem;margin-bottom:1rem;">'
            "Üniversite AI Asistanı</p>",
            unsafe_allow_html=True,
        )
        return
    st.markdown('<h1 class="hero-title">Üniversite AI Asistanı</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hero-subtitle">Yüklenen akademik belgeler, yönetmelikler ve '
        "duyurular üzerinden kaynaklı cevaplar sunar.</p>",
        unsafe_allow_html=True,
    )


def render_suggestion_cards(on_select) -> None:
    if has_messages():
        return
    cols = st.columns(2)
    for i, question in enumerate(DEFAULT_SUGGESTIONS):
        with cols[i % 2]:
            if st.button(question, key=f"suggest_{i}", use_container_width=True):
                on_select(question)


def render_chat_history() -> None:
    for msg in st.session_state.messages:
        role = msg.get("role", "assistant")
        with st.chat_message(role, avatar="🤖" if role == "assistant" else "✍"):
            if role == "user":
                st.markdown(msg.get("content", ""))
            else:
                render_assistant_message(msg)


def render_agent_steps(agent_steps: list[str] | None) -> None:
    if not agent_steps:
        return
    with st.expander("Agent adımları", expanded=False):
        for step in agent_steps:
            st.markdown(f"✓ {step}")


def render_assistant_message(msg: Message) -> None:
    content = msg.get("content", "")
    citations = msg.get("citations") or []
    validation_warning = msg.get("validation_warning")
    retrieval_debug = msg.get("retrieval_debug")
    agent_steps = msg.get("agent_steps")

    if validation_warning:
        st.warning(validation_warning)

    display = strip_inline_sources(content) if citations else content
    st.markdown(display)

    render_agent_steps(agent_steps)
    render_sources(citations)
    render_retrieval_debug(retrieval_debug)


def render_sources(citations: list[dict]) -> None:
    if not citations:
        return

    with st.expander("Kullanılan kaynaklar", expanded=False):
        for i, citation in enumerate(citations, start=1):
            source = citation.get("source", "Bilinmeyen kaynak")
            page = citation.get("page")
            file_name = citation.get("file_name", "")
            chunk_id = citation.get("chunk_id", "")

            if page is not None:
                title = f"{source} — Sayfa {page}"
            else:
                title = source

            st.markdown(f"**{i}. {title}**")
            meta: list[str] = []
            if file_name:
                meta.append(f"Dosya: `{file_name}`")
            if chunk_id and page is None:
                meta.append(f"Referans: `{chunk_id}`")
            if meta:
                st.caption(" · ".join(meta))


def render_retrieval_debug(retrieval_debug: dict | None) -> None:
    """Yalnızca backend DEBUG_RETRIEVAL açıkken gelen alan — geliştirici görünümü."""
    if not retrieval_debug:
        return

    with st.expander("Geliştirici: Retrieval Debug", expanded=False):
        st.caption(f"Sorgu: {retrieval_debug.get('question', '')}")
        for title, key in (
            ("ChromaDB", "chroma_results"),
            ("BM25", "bm25_results"),
            ("Hybrid final", "final_contexts"),
        ):
            chunks = retrieval_debug.get(key) or []
            st.markdown(f"**{title}** ({len(chunks)})")
            for j, ch in enumerate(chunks[:5], start=1):
                page = ch.get("page")
                page_str = f", s. {page}" if page is not None else ""
                st.caption(
                    f"{j}. {ch.get('source', '')}{page_str} · "
                    f"skor {ch.get('score', 0):.3f}"
                )
                preview = ch.get("text_preview", "")
                if preview:
                    st.text(preview[:400])

