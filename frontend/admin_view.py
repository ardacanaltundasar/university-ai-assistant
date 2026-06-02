"""Yönetim Paneli — lokal PoC gözlemlenebilirlik ve operasyon durumu."""

from __future__ import annotations

import os

import streamlit as st

from api_client import ApiClientError, fetch_admin_diagnostics


def _get_admin_password() -> str:
    """Ortam değişkeni yoksa lokal PoC varsayılanı (değer UI'da gösterilmez)."""
    configured = os.getenv("ADMIN_DASHBOARD_PASSWORD", "").strip()
    return configured if configured else "1234"


def _render_admin_login_gate() -> None:
    st.markdown("## Yönetim Paneli")
    st.write(
        "Bu alan sistem durumu ve operasyonel kayıtları içerir. "
        "Lütfen yönetim şifresini girin."
    )
    password = st.text_input(
        "Yönetim şifresi",
        type="password",
        key="admin_password_input",
        autocomplete="off",
    )
    if st.button("Giriş Yap", type="primary", key="admin_login_btn"):
        if password == _get_admin_password():
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Şifre hatalı.")


def _durum_etiketi(deger: str) -> str:
    """API durum değerlerini Türkçe etikete çevirir."""
    return {
        "ready": "hazır",
        "unavailable": "kullanılamıyor",
        "pending": "beklemede",
        "unknown": "bilinmiyor",
        "completed": "tamamlandı",
        "hit": "önbellek isabeti",
        "miss": "önbellek isabetsiz",
    }.get(str(deger).lower(), str(deger))


def _var_yok(mevcut: bool) -> str:
    return "mevcut" if mevcut else "yok"


def _render_operational_readiness(data: dict) -> None:
    system = data.get("system") or {}
    kb = data.get("knowledge_base") or {}

    backend_ok = system.get("backend") == "ready"
    pg_ok = system.get("database") == "ready"
    redis_ok = system.get("redis") == "ready"
    chroma_ok = bool(kb.get("chroma_exists")) and system.get("vector_db") == "ready"
    bm25_ok = bool(kb.get("bm25_index_exists"))
    web_sources = int(kb.get("web_json_count") or 0) > 0 or bool(kb.get("recent_web_json"))
    pdf_sources = int(kb.get("pdf_count") or 0) > 0 or bool(kb.get("recent_pdfs"))
    sample_visible = "include_sample_data" in kb
    crawl_detected = bool(kb.get("recent_web_json")) or int(kb.get("web_json_count") or 0) > 0
    indexed_ok = bool(
        kb.get("chunks_jsonl_exists")
        and kb.get("bm25_index_exists")
        and kb.get("chroma_exists")
        and system.get("vector_db") == "ready"
    )

    checks: list[tuple[str, bool]] = [
        ("Backend erişilebilir mi?", backend_ok),
        ("PostgreSQL bağlantısı hazır mı?", pg_ok),
        ("Redis bağlantısı hazır mı?", redis_ok),
        ("ChromaDB indexi mevcut mu?", chroma_ok),
        ("BM25 indexi mevcut mu?", bm25_ok),
        ("Web kaynak dizini kullanılabilir mi?", web_sources),
        ("PDF kaynak dizini kullanılabilir mi?", pdf_sources),
        ("Örnek veri ayarı görünür mü? (INCLUDE_SAMPLE_DATA)", sample_visible),
        ("Son tarama çıktıları algılandı mı?", crawl_detected),
        ("Son indexlenmiş veriler hazır mı?", indexed_ok),
    ]

    for label, ok in checks:
        st.checkbox(label, value=ok, disabled=True)


def render_admin_page() -> None:
    if not st.session_state.get("admin_authenticated"):
        _render_admin_login_gate()
        return

    header_col, logout_col = st.columns([5, 1])
    with header_col:
        st.markdown("## Yönetim Paneli")
        st.caption("Lokal PoC ortamında sistem ve veri hattı gözlemlenebilirliği.")
    with logout_col:
        st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        if st.button(
            "Yönetim oturumunu kapat",
            key="admin_logout_btn",
            use_container_width=True,
        ):
            st.session_state.admin_authenticated = False
            st.rerun()

    try:
        with st.spinner("Durum bilgileri yükleniyor…"):
            data = fetch_admin_diagnostics()
    except ApiClientError as exc:
        st.error("Backend'e ulaşılamadı veya yönetim paneli verisi alınamadı.")
        st.caption(str(exc.technical))
        return

    system = data.get("system") or {}
    kb = data.get("knowledge_base") or {}
    redis_info = data.get("redis") or {}
    pg = data.get("postgres") or {}

    st.subheader("Sistem Durumu")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Backend", _durum_etiketi(system.get("backend", "unknown")))
    c2.metric("PostgreSQL", _durum_etiketi(system.get("database", "unavailable")))
    c3.metric("Redis", _durum_etiketi(system.get("redis", "unavailable")))
    c4.metric("Vektör veritabanı", _durum_etiketi(system.get("vector_db", "pending")))

    st.markdown("**Chroma / BM25**")
    st.write(
        f"- Koleksiyon: `{system.get('chroma_collection', '')}`\n"
        f"- Chroma yolu: `{system.get('chroma_path', '')}` "
        f"({_var_yok(bool(system.get('chroma_exists')))})\n"
        f"- BM25 yolu: `{system.get('bm25_index_path', '')}` "
        f"({_var_yok(bool(system.get('bm25_index_exists')))})"
    )

    st.markdown("**OpenAI yapılandırması**")
    key_ok = (
        "yapılandırıldı"
        if system.get("openai_api_key_configured")
        else "yapılandırılmadı"
    )
    st.write(
        f"- Sohbet modeli: `{system.get('openai_chat_model', '')}`\n"
        f"- Embedding modeli: `{system.get('openai_embedding_model', '')}`\n"
        f"- API anahtarı durumu: **{key_ok}** (değer gösterilmez)"
    )

    st.markdown("**Çalışma zamanı ayarları**")
    st.write(
        f"- `debug_retrieval`: `{system.get('debug_retrieval')}`\n"
        f"- `enable_redis_cache`: `{system.get('enable_redis_cache')}` "
        f"(TTL {system.get('redis_cache_ttl_seconds')} sn)"
    )

    st.divider()

    st.subheader("Bilgi Tabanı Durumu")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("PDF belge sayısı", kb.get("pdf_count", 0))
    b2.metric("Web JSON kaynağı", kb.get("web_json_count", 0))
    b3.metric("Örnek dosya sayısı", kb.get("sample_count", 0))
    b4.metric("INCLUDE_SAMPLE_DATA", str(kb.get("include_sample_data", True)))

    st.write(
        f"- İşlenmiş parçalar (`chunks.jsonl`): "
        f"{_var_yok(bool(kb.get('chunks_jsonl_exists')))}\n"
        f"- Chroma depolama: {_var_yok(bool(kb.get('chroma_exists')))}\n"
        f"- BM25 index dosyası: {_var_yok(bool(kb.get('bm25_index_exists')))}"
    )

    st.divider()

    st.subheader("Veri Hattı Durumu")
    st.write(
        f"- Vektör index durumu: **{_durum_etiketi(system.get('vector_db', 'pending'))}**\n"
        f"- Indexlenmiş parça dosyası: {_var_yok(bool(kb.get('chunks_jsonl_exists')))}"
    )

    col_web, col_pdf = st.columns(2)
    with col_web:
        st.markdown("**Son web tarama çıktıları** (en fazla 5)")
        for item in kb.get("recent_web_json") or []:
            st.text(f"{item.get('name')} — {item.get('modified_at', '')[:19]}")
        if not kb.get("recent_web_json"):
            st.caption("Kayıtlı web JSON dosyası yok.")
    with col_pdf:
        st.markdown("**Son PDF kaynakları** (en fazla 5)")
        for item in kb.get("recent_pdfs") or []:
            st.text(f"{item.get('name')} — {item.get('modified_at', '')[:19]}")
        if not kb.get("recent_pdfs"):
            st.caption("Kayıtlı PDF dosyası yok.")

    st.divider()

    st.subheader("Önbellek Durumu")
    st.metric("Cevap önbelleği anahtar sayısı", redis_info.get("answer_cache_key_count", 0))
    st.write(f"Redis: **{_durum_etiketi(redis_info.get('status', 'unavailable'))}**")
    samples = redis_info.get("sample_keys") or []
    if samples:
        st.markdown("**Örnek önbellek anahtarları**")
        for key in samples:
            st.code(key)
    else:
        st.caption("Listelenecek anahtar yok (önbellek boş veya Redis kapalı).")
    st.caption("Salt okunur görünüm; önbellek yönetimi bu ekrandan yapılamaz.")

    st.divider()

    st.subheader("Agent Gözlemlenebilirliği")
    if not pg.get("available"):
        st.warning(
            "PostgreSQL kullanılamıyor; agent ve araç metrikleri yüklenemedi."
        )
    else:
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Sohbet oturumu", pg.get("chat_sessions", 0))
        p2.metric("Mesaj", pg.get("chat_messages", 0))
        p3.metric("Agent çalıştırma", pg.get("agent_runs", 0))
        p4.metric("Araç çağrısı", pg.get("tool_calls", 0))

        st.markdown("**Son agent çalıştırmaları** (son 10)")
        runs = pg.get("recent_agent_runs") or []
        if runs:
            st.dataframe(runs, use_container_width=True, hide_index=True)
        else:
            st.caption("Henüz agent çalıştırması kaydı yok.")

        st.markdown("**Araç kullanım özeti**")
        usage = pg.get("tool_usage_summary") or []
        if usage:
            st.dataframe(usage, use_container_width=True, hide_index=True)
        else:
            st.caption("Henüz araç çağrısı kaydı yok.")

        st.markdown("**Son araç çağrıları** (son 10)")
        calls = pg.get("recent_tool_calls") or []
        if calls:
            st.dataframe(calls, use_container_width=True, hide_index=True)
        else:
            st.caption("Henüz araç çağrısı kaydı yok.")

    st.divider()

    st.subheader("Operasyonel Hazırlık")
    st.caption(
        "Mevcut sistem ve veri hattı durumuna göre otomatik kontrol listesi."
    )
    _render_operational_readiness(data)
