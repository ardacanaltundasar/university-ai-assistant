"""Public web crawler — yalnızca izin verilen domain'lerde HTML ve PDF toplar.

Çalıştırma (proje kökünden):
    export PYTHONPATH=.
    python scripts/crawl_website.py

Gerçek üniversite URL'leri kullanıcının .env dosyasında tanımlanmalıdır (.env.example'a bakın).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_USER_AGENT = (
    "UniversityAIAssistant/0.4.0 (+https://github.com; public-source-collector)"
)
MIN_CONTENT_CHARS = 40
SKIP_TAGS = ("script", "style", "nav", "footer", "header", "noscript", "iframe")

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger("crawl_website")


def _load_env() -> None:
    if ENV_FILE.is_file():
        load_dotenv(ENV_FILE)
    else:
        load_dotenv()


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _parse_csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _resolve_path(raw: str, default: Path) -> Path:
    if not raw:
        return default
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return ""
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalized = parsed._replace(
        fragment="",
        path=path,
        params="",
    )
    return urlunparse(normalized)


def host_allowed(host: str, allowed_domains: list[str]) -> bool:
    host = (host or "").lower().strip()
    if not host:
        return False
    for domain in allowed_domains:
        domain = domain.lower().strip()
        if not domain:
            continue
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False


def url_allowed(url: str, allowed_domains: list[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    return host_allowed(parsed.hostname or "", allowed_domains)


def is_pdf_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def safe_slug(text: str, *, max_len: int = 60) -> str:
    text = text.lower().strip()
    text = (
        text.replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    slug = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    if not slug:
        slug = "page"
    return slug[:max_len].strip("-") or "page"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def pdf_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name or "document.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    stem = safe_slug(Path(name).stem, max_len=80)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    return f"{stem}-{digest}.pdf"


def infer_content_type(url: str, title: str) -> str:
    combined = f"{url} {title}".lower()
    rules = [
        (("duyuru",), "announcement"),
        (("yönetmelik", "yonetmelik"), "regulation"),
        (("yönerge", "yonerge"), "directive"),
        (("akademik-takvim", "akademik takvim", "takvim"), "calendar"),
        (("harc", "harç"), "payment"),
        (("yatay-gecis", "yatay geçiş", "yatay gecis"), "transfer"),
        (("formlar", "/form", "form"), "form"),
        (("egitim-planlari", "eğitim planları", "egitim planlari"), "curriculum"),
        (("sss",), "faq"),
        (("iletisim", "iletişim"), "contact"),
    ]
    for keywords, ctype in rules:
        if any(k in combined for k in keywords):
            return ctype
    return "web_page"


def clean_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def extract_text(soup: BeautifulSoup) -> str:
    for tag_name in SKIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body
    if main is None:
        main = soup
    text = main.get_text(separator="\n", strip=True)
    return clean_whitespace(text)


def extract_date(soup: BeautifulSoup) -> str | None:
    for meta_name in ("article:published_time", "og:updated_time", "date"):
        tag = soup.find("meta", attrs={"property": meta_name}) or soup.find(
            "meta", attrs={"name": meta_name}
        )
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        return str(time_tag["datetime"]).strip()
    return None


def extract_pdf_links(soup: BeautifulSoup, base_url: str, allowed_domains: list[str]) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = normalize_url(urljoin(base_url, href))
        if not absolute or not is_pdf_url(absolute):
            continue
        if not url_allowed(absolute, allowed_domains):
            continue
        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)
    return links


def extract_page_links(soup: BeautifulSoup, base_url: str, allowed_domains: list[str]) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = normalize_url(urljoin(base_url, href))
        if not absolute or is_pdf_url(absolute):
            continue
        if not url_allowed(absolute, allowed_domains):
            continue
        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)
    return links


class WebCrawler:
    def __init__(
        self,
        *,
        seed_urls: list[str],
        allowed_domains: list[str],
        output_dir: Path,
        pdf_dir: Path,
        max_pages: int,
        timeout: int,
        delay: float,
        download_pdfs: bool,
        user_agent: str,
    ) -> None:
        self.seed_urls = [normalize_url(u) for u in seed_urls if normalize_url(u)]
        self.allowed_domains = allowed_domains
        self.output_dir = output_dir
        self.pdf_dir = pdf_dir
        self.max_pages = max_pages
        self.timeout = timeout
        self.delay = delay
        self.download_pdfs = download_pdfs
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

        self.visited_urls: set[str] = set()
        self.saved_hashes: set[str] = set()
        self.saved_urls: set[str] = set()
        self.downloaded_pdf_urls: set[str] = set()

        self.stats = {
            "pages_visited": 0,
            "web_documents_saved": 0,
            "pdf_links_found": 0,
            "pdfs_downloaded": 0,
            "skipped_duplicates": 0,
            "errors": 0,
        }

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self._load_existing_state()

    def _load_existing_state(self) -> None:
        for json_path in self.output_dir.glob("*.json"):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict):
                h = data.get("content_hash")
                u = data.get("url")
                if h:
                    self.saved_hashes.add(str(h))
                if u:
                    self.saved_urls.add(normalize_url(str(u)))
        for pdf_path in self.pdf_dir.glob("*.pdf"):
            self.downloaded_pdf_urls.add(pdf_path.name)

    def _sleep(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay)

    def fetch(self, url: str) -> requests.Response | None:
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            final_url = normalize_url(response.url)
            if final_url and final_url != url:
                if not url_allowed(final_url, self.allowed_domains):
                    logger.warning("Yönlendirme izin dışı domain: %s -> %s", url, final_url)
                    return None
                url = final_url
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.error("İstek hatası [%s]: %s", url, exc)
            self.stats["errors"] += 1
            return None

    def download_pdf(self, url: str, *, title: str | None = None) -> bool:
        filename = pdf_filename_from_url(url)
        dest = self.pdf_dir / filename
        if dest.is_file():
            logger.info("PDF zaten mevcut, atlanıyor: %s", filename)
            self.stats["skipped_duplicates"] += 1
            return False

        response = self.fetch(url)
        if response is None:
            return False

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "pdf" not in content_type and not is_pdf_url(url):
            logger.warning("PDF beklenmiyor [%s]: content-type=%s", url, content_type)
            self.stats["errors"] += 1
            return False

        try:
            dest.write_bytes(response.content)
            self.stats["pdfs_downloaded"] += 1
            logger.info("PDF indirildi: %s", dest.name)
            self._save_pdf_metadata(url, title=title, filename=filename)
            return True
        except OSError as exc:
            logger.error("PDF yazma hatası [%s]: %s", url, exc)
            self.stats["errors"] += 1
            return False

    def _save_pdf_metadata(self, url: str, *, title: str | None, filename: str) -> None:
        meta = {
            "title": title or Path(urlparse(url).path).stem.replace("-", " ").title(),
            "url": url,
            "date": None,
            "content": "",
            "source_type": "web",
            "content_type": infer_content_type(url, title or ""),
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": content_hash(url),
            "pdf_links": [url],
            "local_pdf": str(self.pdf_dir / filename),
        }
        slug = safe_slug(meta["title"])
        meta_name = f"{slug}-{meta['content_hash']}.json"
        meta_path = self.output_dir / meta_name
        if meta_path.exists():
            return
        try:
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("PDF metadata yazılamadı: %s", exc)

    def save_web_document(
        self,
        *,
        title: str,
        url: str,
        content: str,
        date: str | None,
        pdf_links: list[str],
    ) -> bool:
        if len(content) < MIN_CONTENT_CHARS:
            logger.info("İçerik çok kısa, atlanıyor: %s", url)
            return False

        digest = content_hash(content)
        if url in self.saved_urls or digest in self.saved_hashes:
            logger.info("Duplicate, atlanıyor: %s", url)
            self.stats["skipped_duplicates"] += 1
            return False

        ctype = infer_content_type(url, title)
        record: dict[str, Any] = {
            "title": title,
            "url": url,
            "date": date,
            "content": content,
            "source_type": "web",
            "content_type": ctype,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": digest,
            "pdf_links": pdf_links,
        }
        slug = safe_slug(title or urlparse(url).path.strip("/").replace("/", "-"))
        file_name = f"{slug}-{digest}.json"
        out_path = self.output_dir / file_name
        try:
            out_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("JSON yazma hatası [%s]: %s", url, exc)
            self.stats["errors"] += 1
            return False

        self.saved_urls.add(url)
        self.saved_hashes.add(digest)
        self.stats["web_documents_saved"] += 1
        logger.info("Kaydedildi: %s", out_path.name)
        return True

    def process_html(self, url: str, response: requests.Response) -> None:
        soup = BeautifulSoup(response.content, "lxml")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else urlparse(url).path
        date = extract_date(soup)
        content = extract_text(soup)
        pdf_links = extract_pdf_links(soup, url, self.allowed_domains)
        self.stats["pdf_links_found"] += len(pdf_links)

        self.save_web_document(
            title=title,
            url=url,
            content=content,
            date=date,
            pdf_links=pdf_links,
        )

        if self.download_pdfs:
            for pdf_url in pdf_links:
                self._sleep()
                self.download_pdf(pdf_url, title=title)

        if self.stats["pages_visited"] < self.max_pages:
            for link in extract_page_links(soup, url, self.allowed_domains):
                if link not in self.visited_urls:
                    self.queue.append(link)

    def process_url(self, url: str) -> None:
        url = normalize_url(url)
        if not url or url in self.visited_urls:
            return
        if not url_allowed(url, self.allowed_domains):
            logger.warning("İzin dışı URL atlandı: %s", url)
            return

        self.visited_urls.add(url)
        self.stats["pages_visited"] += 1
        logger.info("Ziyaret (%d/%d): %s", self.stats["pages_visited"], self.max_pages, url)

        if is_pdf_url(url):
            if self.download_pdfs:
                self.download_pdf(url)
            else:
                logger.info("PDF URL (indirme kapalı): %s", url)
            self._sleep()
            return

        response = self.fetch(url)
        self._sleep()
        if response is None:
            return

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "pdf" in content_type or is_pdf_url(response.url):
            if self.download_pdfs:
                try:
                    filename = pdf_filename_from_url(url)
                    dest = self.pdf_dir / filename
                    if not dest.is_file():
                        dest.write_bytes(response.content)
                        self.stats["pdfs_downloaded"] += 1
                        logger.info("PDF indirildi: %s", dest.name)
                    else:
                        self.stats["skipped_duplicates"] += 1
                except OSError as exc:
                    logger.error("PDF yazma hatası: %s", exc)
                    self.stats["errors"] += 1
            return

        if "html" not in content_type and "text" not in content_type:
            logger.warning("HTML olmayan içerik atlandı [%s]: %s", url, content_type)
            return

        self.process_html(url, response)

    def run(self) -> dict[str, Any]:
        self.queue: deque[str] = deque(self.seed_urls)
        while self.queue and self.stats["pages_visited"] < self.max_pages:
            url = self.queue.popleft()
            self.process_url(url)
        return self.stats


def print_summary(stats: dict[str, Any], *, output_dir: Path, pdf_dir: Path) -> None:
    print("\nCrawler Summary:")
    print(f"  Pages visited       : {stats['pages_visited']}")
    print(f"  Web documents saved : {stats['web_documents_saved']}")
    print(f"  PDF links found     : {stats['pdf_links_found']}")
    print(f"  PDFs downloaded     : {stats['pdfs_downloaded']}")
    print(f"  Skipped duplicates  : {stats['skipped_duplicates']}")
    print(f"  Errors              : {stats['errors']}")
    print(f"  Output directory    : {output_dir}")
    print(f"  PDF directory       : {pdf_dir}")


def main() -> int:
    _load_env()

    seed_urls = _parse_csv_list(os.getenv("UNIVERSITY_CRAWL_URLS"))
    allowed_domains = _parse_csv_list(os.getenv("UNIVERSITY_ALLOWED_DOMAINS"))
    if not allowed_domains:
        allowed_domains = ["medeniyet.edu.tr"]

    output_dir = _resolve_path(
        os.getenv("CRAWLER_OUTPUT_DIR", "").strip(),
        PROJECT_ROOT / "data" / "raw" / "web",
    )
    pdf_dir = _resolve_path(
        os.getenv("CRAWLER_PDF_DIR", "").strip(),
        PROJECT_ROOT / "data" / "raw" / "pdf",
    )

    if not seed_urls:
        print(
            "Hata: UNIVERSITY_CRAWL_URLS boş. .env dosyanıza .env.example'daki örnek URL'leri ekleyin.",
            file=sys.stderr,
        )
        return 1

    crawler = WebCrawler(
        seed_urls=seed_urls,
        allowed_domains=allowed_domains,
        output_dir=output_dir,
        pdf_dir=pdf_dir,
        max_pages=_env_int("CRAWLER_MAX_PAGES", 30),
        timeout=_env_int("CRAWLER_REQUEST_TIMEOUT", 10),
        delay=_env_float("CRAWLER_DELAY_SECONDS", 1.0),
        download_pdfs=_env_bool("CRAWLER_DOWNLOAD_PDFS", True),
        user_agent=os.getenv("CRAWLER_USER_AGENT", DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT,
    )

    logger.info("Başlangıç URL sayısı: %d", len(crawler.seed_urls))
    logger.info("İzin verilen domain'ler: %s", ", ".join(allowed_domains))
    stats = crawler.run()
    print_summary(stats, output_dir=output_dir, pdf_dir=pdf_dir)
    return 0 if stats["errors"] == 0 or stats["web_documents_saved"] + stats["pdfs_downloaded"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
