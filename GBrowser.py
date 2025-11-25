# Gorstak's Browser - PyQt6 with tabs, video support, and fixed bookmarks

import sys
import ctypes
from ctypes import wintypes

_INITIAL_DLLS = set()
_BASELINE_CAPTURED = False

def _capture_baseline_dlls():
    """Capture DLLs at the very start before any injections"""
    global _INITIAL_DLLS, _BASELINE_CAPTURED
    if sys.platform != 'win32' or _BASELINE_CAPTURED:
        return
    
    try:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        
        EnumProcessModules = psapi.EnumProcessModules
        EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        EnumProcessModules.restype = wintypes.BOOL
        
        GetModuleFileNameExW = psapi.GetModuleFileNameExW
        GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        GetModuleFileNameExW.restype = wintypes.DWORD
        
        process_handle = kernel32.GetCurrentProcess()
        hMods = (wintypes.HMODULE * 1024)()
        cbNeeded = wintypes.DWORD()
        
        if EnumProcessModules(process_handle, hMods, ctypes.sizeof(hMods), ctypes.byref(cbNeeded)):
            num_modules = cbNeeded.value // ctypes.sizeof(wintypes.HMODULE)
            for i in range(num_modules):
                if hMods[i]:
                    module_name = ctypes.create_unicode_buffer(260)
                    if GetModuleFileNameExW(process_handle, hMods[i], module_name, 260):
                        if module_name.value:
                            _INITIAL_DLLS.add(module_name.value.lower())
        
        _BASELINE_CAPTURED = True
        print(f"[DLL Protection] Captured {len(_INITIAL_DLLS)} baseline DLLs at script start")
    except Exception as e:
        print(f"[DLL Protection] Failed to capture baseline: {e}")

# Capture immediately!
_capture_baseline_dlls()

# Now do the rest of the imports
import os
import re
import json
import traceback
import threading
import time

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".gorstak_browser")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QToolButton, QMenu, QFileDialog,
    QMessageBox, QSizePolicy, QTabWidget, QTabBar
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor  # Added for ad blocking
)
from PyQt6.QtCore import Qt, QUrl, QSize, QTimer, QByteArray
from PyQt6.QtGui import QFont, QPixmap, QPainter, QIcon, QAction
from PyQt6.QtSvg import QSvgRenderer
from bs4 import BeautifulSoup


AD_DOMAINS = {
    # Major ad networks
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google-analytics.com", "googletagmanager.com", "googletagservices.com",
    "adservice.google.com", "pagead2.googlesyndication.com",
    # Facebook tracking
    "facebook.net", "fbcdn.net", "connect.facebook.net",
    "pixel.facebook.com", "an.facebook.com",
    # Other ad networks
    "adsrvr.org", "adnxs.com", "rubiconproject.com", "pubmatic.com",
    "openx.net", "casalemedia.com", "criteo.com", "criteo.net",
    "outbrain.com", "taboola.com", "mgid.com", "revcontent.com",
    "amazon-adsystem.com", "media.net", "contextweb.com",
    "advertising.com", "adcolony.com", "unity3d.com", "applovin.com",
    "mopub.com", "inmobi.com", "chartboost.com",
    # Tracking/Analytics
    "scorecardresearch.com", "quantserve.com", "hotjar.com",
    "fullstory.com", "mouseflow.com", "crazyegg.com", "luckyorange.com",
    "mixpanel.com", "amplitude.com", "segment.io", "segment.com",
    "branch.io", "adjust.com", "appsflyer.com", "kochava.com",
    "newrelic.com", "nr-data.net", "bugsnag.com", "sentry.io",
    "rollbar.com", "raygun.com",
    # Social tracking
    "addthis.com", "sharethis.com", "addtoany.com",
    "twitter.com/i/adsct", "analytics.twitter.com",
    "linkedin.com/px", "snap.licdn.com",
    "tiktok.com/i18n/pixel", "analytics.tiktok.com",
    # Misc trackers
    "omtrdc.net", "demdex.net", "everesttech.net",  # Adobe
    "bing.com/bat.js", "bat.bing.com",  # Microsoft
    "yandex.ru/metrika", "mc.yandex.ru",  # Yandex
    "gemius.pl", "hit.gemius.pl",
    "2mdn.net", "serving-sys.com", "eyeota.net", "bluekai.com",
    "exelator.com", "crwdcntrl.net", "rlcdn.com", "pippio.com",
    "tapad.com", "adform.net", "adsymptotic.com", "adgrx.com",
    # Popup/overlay annoyances
    "pushwoosh.com", "onesignal.com", "pusher.com", "subscribers.com",
    "popads.net", "popcash.net", "propellerads.com",
}

AD_URL_PATTERNS = [
    r"/ads/", r"/ad/", r"/adserver", r"/advert", r"/banner",
    r"doubleclick", r"googlesyndication", r"googleads",
    r"/pagead/", r"/pixel", r"/tracking", r"/tracker",
    r"amazon-adsystem", r"/sponsored", r"smartadserver",
]


class AdBlocker(QWebEngineUrlRequestInterceptor):
    """Request interceptor to block ads and trackers"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.blocked_count = 0
        self.enabled = True
    
    def interceptRequest(self, info):
        if not self.enabled:
            return
            
        url = info.requestUrl().toString().lower()
        host = info.requestUrl().host().lower()
        
        # Check if host matches any ad domain
        for ad_domain in AD_DOMAINS:
            if host == ad_domain or host.endswith("." + ad_domain):
                info.block(True)
                self.blocked_count += 1
                return
        
        # Check URL patterns
        for pattern in AD_URL_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                info.block(True)
                self.blocked_count += 1
                return


# Small SVG helpers
OVERFLOW_SVG = '<svg width="20" height="20"><path d="M6 10c0-1.1.9-2 2-2s2 .9 2 2-.9 2-2 2-2-.9-2-2z" fill="#ccc"/></svg>'
NEW_TAB_SVG = '<svg width="20" height="20"><path d="M10 4v6h6v2h-6v6H8v-6H2v-2h6V4h2z" fill="#ccc"/></svg>'
CLOSE_SVG = '<svg width="12" height="12"><path d="M2 2l8 8M10 2l-8 8" stroke="#ccc" stroke-width="2"/></svg>'

def svg_icon(svg, size=20):
    r = QSvgRenderer(QByteArray(svg.encode()))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    r.render(p)
    p.end()
    return QIcon(pix)


class CustomWebPage(QWebEnginePage):
    def __init__(self, profile, parent=None, browser=None):
        super().__init__(profile, parent)
        self._browser = browser
        
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.HyperlinkAuditingEnabled, False)
        
        self.featurePermissionRequested.connect(self._handle_permission_request)
    
    def _handle_permission_request(self, url, feature):
        self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)
    
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        return True
    
    def createWindow(self, window_type):
        if self._browser:
            return self._browser.create_new_tab()
        return None


class BrowserTab(QWebEngineView):
    def __init__(self, profile, browser, url=None):
        super().__init__()
        self._browser = browser
        page = CustomWebPage(profile, self, browser)
        self.setPage(page)
        if url:
            self.setUrl(QUrl(url))


class Browser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gorstak's Browser")
        self.setMinimumSize(800, 600)
        self.setWindowFlags(Qt.WindowType.Window)

        self.config = self._load_config()
        
        geom = self.config.get("geometry", {})
        self.setGeometry(
            geom.get("x", 100),
            geom.get("y", 100),
            geom.get("width", 1280),
            geom.get("height", 820)
        )
        if geom.get("maximized", False):
            self.showMaximized()

        central = QWidget()
        central.setStyleSheet("background:#1e1e1e;")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        nav = QWidget()
        nav.setFixedHeight(64)
        nav.setStyleSheet("background:#252526;")
        nlay = QHBoxLayout(nav)
        nlay.setContentsMargins(12, 8, 12, 8)
        nlay.setSpacing(12)

        self.profile = QWebEngineProfile("GBrowser", self)
        self.profile.setPersistentStoragePath(os.path.join(CONFIG_DIR, "storage"))
        self.profile.setCachePath(os.path.join(CONFIG_DIR, "cache"))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        
        self.ad_blocker = AdBlocker(self)
        self.profile.setUrlRequestInterceptor(self.ad_blocker)
        
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 0; }
            QTabBar::tab {
                background: #2d2d2d;
                color: #ccc;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                min-width: 120px;
                max-width: 200px;
            }
            QTabBar::tab:selected {
                background: #3c3c3c;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background: #353535;
            }
            QTabBar::close-button {
                image: none;
                subcontrol-position: right;
            }
        """)
        
        last_url = self.config.get("last_url", "https://www.google.com")
        self._add_tab(last_url)

        back_svg = '<svg width="24" height="24"><path d="M20 11 H7.83 l5.59-5.59 L12 4 l-8 8 8 8 1.41-1.41 L7.83 13 H20 v-2 z" fill="#ccc"/></svg>'
        forward_svg = '<svg width="24" height="24"><path d="M12 4 l-1.41 1.41 L16.17 11 H4 v2 h12.17 l-5.58 5.59 L12 20 l8-8 z" fill="#ccc"/></svg>'
        reload_svg = '<svg width="24" height="24"><path d="M17.65 6.35 C16.2 4.9 14.21 4 12 4 c-4.42 0-7.99 3.58-7.99 8 s3.57 8 7.99 8 c3.73 0 6.84-2.55 7.73-6 h-2.08 c-.82 2.33-3.04 4-5.65 4 -3.31 0-6-2.69-6-6 s2.69-6 6-6 c1.66 0 3.14.69 4.22 1.78 L13 11 h7 V4 l-2.35 2.35 z" fill="#ccc"/></svg>'
        home_svg = '<svg width="24" height="24"><path d="M10 20 v-6 h4 v6 h5 v-8 h3 L12 3 2 12 h3 v8 z" fill="#ccc"/></svg>'

        for svg, func in zip([back_svg, forward_svg, reload_svg, home_svg],
                             [self._go_back, self._go_forward, self._reload,
                              lambda: self._current_browser().setUrl(QUrl("https://www.google.com"))]):
            btn = QPushButton()
            btn.setFixedSize(48, 48)
            btn.setIcon(svg_icon(svg))
            btn.setIconSize(QSize(24, 24))
            btn.setStyleSheet("""
                QPushButton { background:#3c3c3c; border-radius:24px; }
                QPushButton:hover { background:#505050; }
                QPushButton:pressed { background:#606060; }
            """)
            btn.clicked.connect(func)
            nlay.addWidget(btn)

        new_tab_btn = QPushButton()
        new_tab_btn.setFixedSize(48, 48)
        new_tab_btn.setIcon(svg_icon(NEW_TAB_SVG))
        new_tab_btn.setIconSize(QSize(24, 24))
        new_tab_btn.setStyleSheet("""
            QPushButton { background:#3c3c3c; border-radius:24px; }
            QPushButton:hover { background:#505050; }
            QPushButton:pressed { background:#606060; }
        """)
        new_tab_btn.setToolTip("New Tab")
        new_tab_btn.clicked.connect(lambda: self._add_tab("https://www.google.com"))
        nlay.addWidget(new_tab_btn)

        # Bookmarks import button (B)
        self.btnB = QPushButton("B")
        self.btnB.setFixedSize(48, 48)
        self.btnB.setStyleSheet("""
            QPushButton { background:#3c3c3c; color:white; border-radius:24px; font-size:18px; }
            QPushButton:hover { background:#505050; }
            QPushButton:pressed { background:#606060; }
        """)
        self.btnB.clicked.connect(self.open_bookmarks_file)
        nlay.addWidget(self.btnB)

        # URL bar
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Search or enter address")
        self.url_bar.setFont(QFont("Segoe UI", 11))
        self.url_bar.setStyleSheet("""
            QLineEdit { background:#3c3c3c; color:white; border-radius:26px;
                        padding: 0px 20px; min-height: 44px; }
            QLineEdit:focus { background:#454545; border: 2px solid #0a84ff; padding: 0px 18px; }
        """)
        self.url_bar.returnPressed.connect(self.navigate)

        url_container = QWidget()
        url_container.setStyleSheet("background:#3c3c3c; border-radius:26px;")
        url_container.setFixedHeight(52)
        url_lay = QHBoxLayout(url_container)
        url_lay.setContentsMargins(0, 0, 0, 0)
        url_lay.addWidget(self.url_bar)
        nlay.addWidget(url_container, 1)

        self.profile.downloadRequested.connect(self.handle_download)

        layout.addWidget(nav)

        # Bookmarks bar
        self.bookmarks_bar_widget = QWidget()
        self.bookmarks_bar_widget.setFixedHeight(48)
        self.bookmarks_bar_widget.setStyleSheet("background:#2d2d2d;")
        bb_layout = QHBoxLayout(self.bookmarks_bar_widget)
        bb_layout.setContentsMargins(8, 6, 8, 6)
        bb_layout.setSpacing(6)

        self.bookmarks_container = QWidget()
        self.bookmarks_container_layout = QHBoxLayout(self.bookmarks_container)
        self.bookmarks_container_layout.setContentsMargins(0, 0, 0, 0)
        self.bookmarks_container_layout.setSpacing(6)
        bb_layout.addWidget(self.bookmarks_container)

        self.overflow_btn = QPushButton()
        self.overflow_btn.setFixedSize(32, 32)
        self.overflow_btn.setIcon(svg_icon(OVERFLOW_SVG))
        self.overflow_btn.setStyleSheet("""
            QPushButton { background:#3c3c3c; border-radius:16px; }
            QPushButton:hover { background:#505050; }
        """)
        self.overflow_btn.setVisible(False)
        self.overflow_btn.clicked.connect(self.show_overflow_menu)
        bb_layout.addWidget(self.overflow_btn)

        layout.addWidget(self.bookmarks_bar_widget)
        layout.addWidget(self.tabs, 1)

        # internal data
        self.bookmarks = []
        self.overflow_items = []
        self._overflow_timer = QTimer()
        self._overflow_timer.setSingleShot(True)
        self._overflow_timer.timeout.connect(self._evaluate_overflow)
        self.resizeEvent = self._on_resize_override
        
        saved_bookmarks = self.config.get("bookmarks", [])
        if saved_bookmarks:
            self.bookmarks = saved_bookmarks
            self._rebuild_bookmarks_bar()

        # Initialize DLL protection
        self.dll_protection = DLLProtection()

    def _add_tab(self, url="https://www.google.com"):
        tab = BrowserTab(self.profile, self, url)
        tab.titleChanged.connect(lambda title, t=tab: self._update_tab_title(t, title))
        tab.urlChanged.connect(lambda url, t=tab: self._update_url_bar(t, url))
        idx = self.tabs.addTab(tab, "New Tab")
        self.tabs.setCurrentIndex(idx)
        return tab
    
    def create_new_tab(self, url=None):
        """Called by CustomWebPage.createWindow for target=_blank links"""
        tab = BrowserTab(self.profile, self, url)
        tab.titleChanged.connect(lambda title, t=tab: self._update_tab_title(t, title))
        tab.urlChanged.connect(lambda url, t=tab: self._update_url_bar(t, url))
        idx = self.tabs.addTab(tab, "New Tab")
        self.tabs.setCurrentIndex(idx)
        return tab.page()
    
    def close_tab(self, index):
        if self.tabs.count() > 1:
            widget = self.tabs.widget(index)
            self.tabs.removeTab(index)
            widget.deleteLater()
        else:
            # Last tab - close window
            self.close()
    
    def _update_tab_title(self, tab, title):
        idx = self.tabs.indexOf(tab)
        if idx >= 0:
            short_title = title[:25] + "..." if len(title) > 25 else title
            self.tabs.setTabText(idx, short_title or "New Tab")
    
    def _update_url_bar(self, tab, url):
        if tab == self._current_browser():
            self.url_bar.setText(url.toString())
    
    def _on_tab_changed(self, index):
        if not hasattr(self, 'url_bar'):
            return
        browser = self._current_browser()
        if browser:
            self.url_bar.setText(browser.url().toString())
    
    def _current_browser(self):
        return self.tabs.currentWidget()
    
    def _go_back(self):
        b = self._current_browser()
        if b:
            b.back()
    
    def _go_forward(self):
        b = self._current_browser()
        if b:
            b.forward()
    
    def _reload(self):
        b = self._current_browser()
        if b:
            b.reload()

    def _load_config(self):
        """Load config from file"""
        if not os.path.exists(CONFIG_FILE):
            return {}
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_config(self):
        """Save config to file"""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        
        geom = self.geometry()
        self.config["geometry"] = {
            "x": geom.x(),
            "y": geom.y(),
            "width": geom.width(),
            "height": geom.height(),
            "maximized": self.isMaximized()
        }
        
        browser = self._current_browser()
        if browser:
            self.config["last_url"] = browser.url().toString()
        self.config["bookmarks"] = self.bookmarks
        
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Failed to save config: {e}")

    # ------------------------
    # Bookmarks file handling
    # ------------------------
    def open_bookmarks_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Bookmarks HTML", "", "HTML Files (*.html *.htm);;All Files (*)")
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                html = f.read()
            self._parse_bookmarks_html(html)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open bookmarks file:\n{e}")

    def _parse_bookmarks_html(self, html):
        try:
            soup = BeautifulSoup(html, "html5lib")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")
        
        def parse_dl(dl_tag, depth=0):
            """Robust recursive parser for Netscape-style bookmarks HTML."""
            nodes = []
            
            all_dts = dl_tag.find_all("dt")
            direct_dts = []
            for dt in all_dts:
                parent = dt.parent
                while parent and parent.name != "dl":
                    parent = parent.parent
                if parent is dl_tag:
                    direct_dts.append(dt)
            
            for dt in direct_dts:
                a = dt.find("a", recursive=False) or dt.find("a")
                h3 = dt.find(["h3", "h1", "h2"], recursive=False) or dt.find(["h3", "h1", "h2"])

                if a and h3:
                    elem_str = str(dt)
                    h3_pos = elem_str.find(str(h3))
                    a_pos = elem_str.find(str(a))
                    if h3_pos < a_pos:
                        a = None
                    else:
                        h3 = None

                if a and not h3:
                    title = (a.get_text(strip=True) or a.get("href") or "").strip()
                    href = a.get("href")
                    if href:
                        nodes.append({"type": "link", "title": title or href, "href": href})
                    continue

                if h3:
                    folder_title = (h3.get_text(strip=True) or "Folder").strip()
                    children = []

                    sibling = dt.next_sibling
                    while sibling:
                        if hasattr(sibling, 'name'):
                            if sibling.name == "dl":
                                children = parse_dl(sibling, depth + 1)
                                break
                            elif sibling.name == "dt":
                                break
                        sibling = sibling.next_sibling
                    
                    if not children:
                        child_dl = dt.find("dl")
                        if child_dl:
                            children = parse_dl(child_dl, depth + 1)
                    
                    nodes.append({"type": "folder", "title": folder_title, "children": children})

            return nodes

        top_dl = soup.find("dl")
        if top_dl:
            parsed = parse_dl(top_dl)
            if len(parsed) == 1 and parsed[0].get("type") == "folder":
                parsed = parsed[0].get("children", parsed)
        else:
            parsed = []
            for a in soup.find_all("a"):
                href = a.get("href")
                if href:
                    parsed.append({
                        "type": "link",
                        "title": (a.get_text(strip=True) or href).strip(),
                        "href": href
                    })

        self.bookmarks = parsed
        self._rebuild_bookmarks_bar()

    # ------------------------
    # Build bookmarks bar UI
    # ------------------------
    def _clear_bookmarks_container(self):
        while self.bookmarks_container_layout.count():
            item = self.bookmarks_container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _rebuild_bookmarks_bar(self):
        self._clear_bookmarks_container()
        self.overflow_items = []

        if not self.bookmarks:
            label = QLabel("No bookmarks loaded")
            label.setStyleSheet("color: #666; padding: 6px 10px;")
            self.bookmarks_container_layout.addWidget(label)
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.bookmarks_container_layout.addWidget(spacer)
            return

        for node in self.bookmarks:
            if node["type"] == "link":
                btn = QPushButton(node.get("title", node.get("href", "untitled")))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setProperty("href", node.get("href"))
                btn.setStyleSheet("""
                    QPushButton { background:#3c3c3c; color:white; border-radius:6px; padding:6px 10px; }
                    QPushButton:hover { background:#505050; }
                """)
                btn.clicked.connect(lambda checked, h=node.get("href"): self._open_href(h))
                self.bookmarks_container_layout.addWidget(btn)
            elif node["type"] == "folder":
                tb = QToolButton()
                tb.setText(node.get("title", "Folder"))
                tb.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                tb.setStyleSheet("""
                    QToolButton { background:#3c3c3c; color:white; border-radius:6px; padding:6px 10px; }
                    QToolButton:hover { background:#505050; }
                """)
                menu = QMenu()

                def add_children(m, children):
                    for c in children:
                        if c["type"] == "link":
                            a = QAction(c.get("title", c.get("href")), self)
                            href = c.get("href")
                            a.triggered.connect(lambda checked, h=href: self._open_href(h))
                            m.addAction(a)
                        elif c["type"] == "folder":
                            sub = QMenu(c.get("title", "Folder"), self)
                            add_children(sub, c.get("children", []))
                            m.addMenu(sub)

                add_children(menu, node.get("children", []))
                tb.setMenu(menu)
                self.bookmarks_container_layout.addWidget(tb)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.bookmarks_container_layout.addWidget(spacer)
        self._overflow_timer.start(120)

    def _open_href(self, href):
        if not href:
            return
        if href.startswith("javascript:") or href.startswith("data:"):
            QMessageBox.information(self, "Unsupported", "Bookmark uses a javascript/data URL which cannot be opened.")
            return
        if not href.startswith(("http://", "https://")):
            href = "https://" + href
        # Open in new tab
        self._add_tab(href)

    # ------------------------
    # Overflow
    # ------------------------
    def _on_resize_override(self, event):
        QMainWindow.resizeEvent(self, event)
        self._overflow_timer.start(120)

    def _evaluate_overflow(self):
        available = self.bookmarks_bar_widget.width() - 80
        total = 0
        widgets = []

        for i in range(self.bookmarks_container_layout.count()):
            it = self.bookmarks_container_layout.itemAt(i)
            w = it.widget()
            if w is None:
                continue
            if isinstance(w, QWidget) and w.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding:
                break
            w.adjustSize()
            w_w = w.width() if w.width() > 0 else w.sizeHint().width()
            widgets.append((w, w_w))
            total += w_w + self.bookmarks_container_layout.spacing()

        if total <= available:
            for w, _ in widgets:
                w.setVisible(True)
            self.overflow_items = []
            self.overflow_btn.setVisible(False)
            return

        used = 0
        shown = []
        overflow = []
        for w, w_w in widgets:
            if used + w_w + self.bookmarks_container_layout.spacing() <= available:
                shown.append(w)
                used += w_w + self.bookmarks_container_layout.spacing()
            else:
                overflow.append(w)

        for w, _ in widgets:
            w.setVisible(w in shown)

        self.overflow_items = []
        for w in overflow:
            if isinstance(w, QToolButton):
                self.overflow_items.append({"type": "folder", "title": w.text(), "menu": w.menu()})
            elif isinstance(w, QPushButton):
                self.overflow_items.append({"type": "link", "title": w.text(), "href": w.property("href")})

        self.overflow_btn.setVisible(bool(self.overflow_items))

    def show_overflow_menu(self):
        if not self.overflow_items:
            return
        menu = QMenu()
        for it in self.overflow_items:
            if it["type"] == "link":
                act = QAction(it["title"], self)
                h = it.get("href")
                act.triggered.connect(lambda checked, href=h: self._open_href(href))
                menu.addAction(act)
            elif it["type"] == "folder":
                sub = QMenu(it["title"], self)
                src_menu = it.get("menu")

                def clone_menu(src, dst):
                    for a in src.actions():
                        if a.menu():
                            child = QMenu(a.text(), self)
                            clone_menu(a.menu(), child)
                            dst.addMenu(child)
                        else:
                            new = QAction(a.text(), self)
                            new.triggered.connect(lambda checked, t=a.text(): self._open_href(self._find_href_by_title(t)))
                            dst.addAction(new)

                if src_menu:
                    clone_menu(src_menu, sub)
                menu.addMenu(sub)
        menu.exec(self.overflow_btn.mapToGlobal(self.overflow_btn.rect().bottomLeft()))

    def _find_href_by_title(self, title):
        queue = list(self.bookmarks)
        while queue:
            node = queue.pop(0)
            if node["type"] == "link" and node.get("title") == title:
                return node.get("href")
            if node["type"] == "folder":
                queue = node.get("children", []) + queue
        return ""

    # ------------------------
    # Navigation & downloads
    # ------------------------
    def navigate(self):
        url = self.url_bar.text().strip()
        if not url:
            return
        if " " in url and "." not in url:
            url = "https://www.google.com/search?q=" + url.replace(" ", "+")
        elif not url.startswith(("http://", "https://")):
            url = "https://" + url
        browser = self._current_browser()
        if browser:
            browser.setUrl(QUrl(url))

    def handle_download(self, item):
        path, _ = QFileDialog.getSaveFileName(self, "Save File", item.suggestedFileName())
        if path:
            item.setDownloadDirectory(os.path.dirname(path))
            item.setDownloadFileName(os.path.basename(path))
            item.accept()

    def closeEvent(self, event):
        self._save_config()
        
        # Close all tabs
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if widget:
                widget.stop()
                widget.load(QUrl("about:blank"))
        
        # Stop DLL protection
        self.dll_protection.stop()
        
        super().closeEvent(event)


class DLLProtection:
    """Aggressively removes ANY DLL injected after script start"""
    
    # Whitelist patterns for Qt/Python lazy-loaded DLLs only
    ALLOWED_PATHS = (
        "\\python",
        "\\pyqt6",
        "\\qt6",
        "\\windows\\system32",
        "\\windows\\syswow64",
        "\\windows\\winsxs",
        "\\nvidia",
        "\\amd",
        "\\intel",
        "\\program files\\common files\\microsoft",
        "\\program files (x86)\\common files\\microsoft",
        "\\program files\\windows",
        "\\program files (x86)\\windows",
        "\\microsoft.vc",
        "\\vcruntime",
        "\\msvcp",
        "\\msvcr",
        "\\directx",
        "\\microsoft shared",
        "\\shell",
        "\\microsoft.net",
        "\\dotnet",
        "\\windows defender",
        "\\programdata\\microsoft",
    )
    
    def __init__(self):
        self.running = False
        self.check_interval = 0.05  # 50ms
        self.monitor_thread = None
        # Use the baseline captured at script start
        self.initial_dlls = set(_INITIAL_DLLS)
        print(f"[DLL Protection] Initialized with {len(self.initial_dlls)} baseline DLLs")
    
    def start(self):
        """Start monitoring for injected DLLs"""
        if self.running:
            return
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("[DLL Protection] Monitoring started - will remove injected DLLs")
    
    def _is_allowed_lazy_dll(self, path):
        """Check if this DLL is allowed to load after startup (Qt/Python/System)"""
        path_lower = path.lower()
        for allowed in self.ALLOWED_PATHS:
            if allowed in path_lower:
                return True
        return False
    
    def _get_loaded_dlls(self):
        """Get list of currently loaded DLLs"""
        dlls = []
        try:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            psapi = ctypes.WinDLL('psapi', use_last_error=True)
            
            EnumProcessModules = psapi.EnumProcessModules
            EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
            EnumProcessModules.restype = wintypes.BOOL
            
            GetModuleFileNameExW = psapi.GetModuleFileNameExW
            GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
            GetModuleFileNameExW.restype = wintypes.DWORD
            
            process_handle = kernel32.GetCurrentProcess()
            hMods = (wintypes.HMODULE * 1024)()
            cbNeeded = wintypes.DWORD()
            
            if EnumProcessModules(process_handle, hMods, ctypes.sizeof(hMods), ctypes.byref(cbNeeded)):
                num_modules = cbNeeded.value // ctypes.sizeof(wintypes.HMODULE)
                for i in range(num_modules):
                    if hMods[i]:
                        module_name = ctypes.create_unicode_buffer(260)
                        if GetModuleFileNameExW(process_handle, hMods[i], module_name, 260):
                            if module_name.value:
                                dlls.append((hMods[i], module_name.value))
        except Exception as e:
            pass
        return dlls
    
    def _unload_dll(self, handle, path):
        """Forcefully unload an injected DLL"""
        try:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            FreeLibrary = kernel32.FreeLibrary
            FreeLibrary.argtypes = [wintypes.HMODULE]
            FreeLibrary.restype = wintypes.BOOL
            
            for _ in range(20):
                if not FreeLibrary(handle):
                    break
            print(f"[DLL Protection] REMOVED: {path}")
            return True
        except Exception as e:
            print(f"[DLL Protection] Failed to remove {path}: {e}")
        return False
    
    def _monitor_loop(self):
        """Background thread that removes injected DLLs"""
        while self.running:
            try:
                time.sleep(self.check_interval)
                
                for handle, path in self._get_loaded_dlls():
                    path_lower = path.lower()
                    
                    # Skip if it was in baseline
                    if path_lower in self.initial_dlls:
                        continue
                    
                    # Allow Qt/Python/System DLLs to load lazily
                    if self._is_allowed_lazy_dll(path):
                        self.initial_dlls.add(path_lower)
                        continue
                    
                    # Remove everything else
                    print(f"[DLL Protection] DETECTED INJECTION: {path}")
                    self._unload_dll(handle, path)
                    self.initial_dlls.add(path_lower)  # Don't spam
                    
            except Exception:
                pass
    
    def stop(self):
        """Stop the monitoring thread"""
        self.running = False
        print("[DLL Protection] Stopped")


_dll_protection = None


if __name__ == "__main__":
    print("[DEBUG] Starting...")
    try:
        if sys.platform == 'win32':
            print("[DEBUG] Creating DLL protection...")
            _dll_protection = DLLProtection()
        
        print("[DEBUG] Creating QApplication...")
        app = QApplication(sys.argv)
        print("[DEBUG] QApplication created")
        app.setApplicationName("Gorstak's Browser")
        print("[DEBUG] Creating Browser window...")
        win = Browser()
        print("[DEBUG] Browser created, showing...")
        win.show()
        
        if _dll_protection:
            print("[DEBUG] Starting DLL protection monitoring...")
            _dll_protection.start()
        
        print("[DEBUG] Entering event loop...")
        exit_code = app.exec()
        
        if _dll_protection:
            _dll_protection.stop()
        
        sys.exit(exit_code)
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        input("Press Enter to exit...")
