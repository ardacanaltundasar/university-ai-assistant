"""Streamlit için global CSS — dark/light uyumlu, sade kurumsal görünüm."""

CUSTOM_CSS = """
<style>
/* Ana alan */
.block-container {
    padding-top: 1.25rem;
    padding-bottom: 6rem;
    max-width: 52rem;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(30, 41, 59, 0.45) 0%, rgba(15, 23, 42, 0.2) 100%);
    border-right: 1px solid rgba(148, 163, 184, 0.12);
}
section[data-testid="stSidebar"] .block-container {
    padding-top: 1.5rem;
}

.sidebar-brand {
    font-size: 1.05rem;
    font-weight: 650;
    letter-spacing: -0.02em;
    line-height: 1.35;
    margin-bottom: 0.15rem;
    color: inherit;
}
.sidebar-brand-sub {
    font-size: 0.72rem;
    opacity: 0.65;
    line-height: 1.4;
    margin-bottom: 1.25rem;
}

/* Ana başlık (boş ekran) */
.hero-title {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    margin: 0 0 0.5rem 0;
    line-height: 1.2;
}
.hero-subtitle {
    font-size: 1rem;
    opacity: 0.72;
    margin: 0 0 2rem 0;
    line-height: 1.55;
    max-width: 36rem;
}

/* Öneri kartları */
div[data-testid="column"] .stButton > button {
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.22);
    background: rgba(148, 163, 184, 0.06);
    padding: 0.85rem 1rem;
    min-height: 4.5rem;
    text-align: left;
    white-space: normal;
    line-height: 1.45;
    font-weight: 500;
    transition: border-color 0.15s, background 0.15s;
}
div[data-testid="column"] .stButton > button:hover {
    border-color: rgba(99, 102, 241, 0.45);
    background: rgba(99, 102, 241, 0.08);
}

/* Yeni sohbet butonu */
div.new-chat-btn .stButton > button {
    border-radius: 10px;
    font-weight: 600;
    border: 1px solid rgba(99, 102, 241, 0.35);
    background: rgba(99, 102, 241, 0.12);
}
div.new-chat-btn .stButton > button:hover {
    background: rgba(99, 102, 241, 0.2);
}

/* Sohbet listesi placeholder */
.chat-list-item {
    font-size: 0.88rem;
    padding: 0.55rem 0.65rem;
    border-radius: 8px;
    margin-bottom: 0.25rem;
    opacity: 0.55;
    border: 1px dashed rgba(148, 163, 184, 0.2);
}
.sidebar-footer {
    font-size: 0.75rem;
    opacity: 0.5;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid rgba(148, 163, 184, 0.15);
}

/* Chat input */
.stChatInput {
    border-radius: 14px;
}
div[data-testid="stChatInput"] textarea {
    border-radius: 14px !important;
}

/* Kaynak expander */
.sources-expander {
    margin-top: 0.75rem;
}

/* Gizle Streamlit üst menü kalabalığı (isteğe bağlı hafif) */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* Mesaj balonları — hafif kart hissi */
[data-testid="stChatMessage"] {
    border-radius: 12px;
}
</style>
"""
