# Gorstak's Browser - PyQt6 version with fixed bookmarks parser
import os
import sys
import re
import json
import traceback

# Config file path for persistence
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".gorstak_browser")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox "
    "--disable-blink-features=AutomationControlled "
    "--disable-features=WebRtcHideLocalIpsWithMdns,IsolateOrigins,site-per-process "
    "--enable-features=WebRTCPipeWireCapturer,NetworkService,NetworkServiceInProcess "
    "--enable-accelerated-2d-canvas "
    "--enable-gpu-rasterization "
    "--enable-webgl "
    "--enable-webgl2 "
    "--ignore-gpu-blocklist "
    "--autoplay-policy=no-user-gesture-required "
    "--disable-site-isolation-trials "
    "--enable-javascript-harmony "
    "--disable-ipc-flooding-protection "
    "--disable-renderer-backgrounding "
    "--disable-backgrounding-occluded-windows "
    "--force-color-profile=srgb "
)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QToolButton, QMenu, QFileDialog,
    QMessageBox, QSizePolicy
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings
)
from PyQt6.QtCore import Qt, QUrl, QSize, QTimer, QByteArray
from PyQt6.QtGui import QFont, QPixmap, QPainter, QIcon, QAction
from PyQt6.QtSvg import QSvgRenderer
from bs4 import BeautifulSoup

# Small SVG helpers
OVERFLOW_SVG = '<svg width="20" height="20"><path d="M6 10c0-1.1.9-2 2-2s2 .9 2 2-.9 2-2 2-2-.9-2-2z" fill="#ccc"/></svg>'

def svg_icon(svg, size=20):
    r = QSvgRenderer(QByteArray(svg.encode()))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)  # PyQt6 enum
    p = QPainter(pix)
    r.render(p)
    p.end()
    return QIcon(pix)

class CustomWebPage(QWebEnginePage):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        
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
        
        self.featurePermissionRequested.connect(self._handle_permission_request)
    
    def javaScriptConsoleMessage(self, level, message, line, source):
        """Print JavaScript console messages for debugging"""
        level_names = {
            QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel: "INFO",
            QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: "WARN",
            QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: "ERROR"
        }
        print(f"[JS {level_names.get(level, 'LOG')}] {source}:{line} - {message}")
    
    def _handle_permission_request(self, url, feature):
        self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)
    
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        return True
    
    def createWindow(self, window_type):
        return self


class Browser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gorstak's Browser")
        self.setMinimumSize(800, 600)
        self.setWindowFlags(Qt.WindowType.Window)  # PyQt6 enum

        self.config = self._load_config()
        
        # Apply saved window geometry
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

        # Top nav
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
        self.profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        )
        
        script = QWebEngineScript()
        script.setName("antibot")
        script.setSourceCode("""
            (function() {
                'use strict';
                
                // Core webdriver hiding
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                
                // Delete automation indicators
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                
                // Realistic navigator properties
                const nav = {
                    plugins: (function() {
                        const plugins = [
                            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                        ];
                        plugins.item = i => plugins[i];
                        plugins.namedItem = name => plugins.find(p => p.name === name);
                        plugins.refresh = () => {};
                        return plugins;
                    })(),
                    languages: ['en-US', 'en'],
                    language: 'en-US',
                    platform: 'Win32',
                    vendor: 'Google Inc.',
                    hardwareConcurrency: 8,
                    deviceMemory: 8,
                    maxTouchPoints: 0,
                    cookieEnabled: true,
                    doNotTrack: null,
                    appCodeName: 'Mozilla',
                    appName: 'Netscape',
                    appVersion: '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
                    product: 'Gecko',
                    productSub: '20030107',
                    vendorSub: ''
                };
                
                for (const [key, value] of Object.entries(nav)) {
                    try {
                        Object.defineProperty(navigator, key, { get: () => value, configurable: true });
                    } catch(e) {}
                }
                
                // Chrome object for Discord
                window.chrome = {
                    app: { isInstalled: false, InstallState: {DISABLED:'disabled',INSTALLED:'installed',NOT_INSTALLED:'not_installed'}, RunningState: {CANNOT_RUN:'cannot_run',READY_TO_RUN:'ready_to_run',RUNNING:'running'}, getDetails: () => null, getIsInstalled: () => false },
                    runtime: {
                        OnInstalledReason: {CHROME_UPDATE:'chrome_update',INSTALL:'install',SHARED_MODULE_UPDATE:'shared_module_update',UPDATE:'update'},
                        OnRestartRequiredReason: {APP_UPDATE:'app_update',OS_UPDATE:'os_update',PERIODIC:'periodic'},
                        PlatformArch: {ARM:'arm',ARM64:'arm64',MIPS:'mips',MIPS64:'mips64',X86_32:'x86-32',X86_64:'x86-64'},
                        PlatformNaclArch: {ARM:'arm',MIPS:'mips',MIPS64:'mips64',X86_32:'x86-32',X86_64:'x86-64'},
                        PlatformOs: {ANDROID:'android',CROS:'cros',LINUX:'linux',MAC:'mac',OPENBSD:'openbsd',WIN:'win'},
                        RequestUpdateCheckStatus: {NO_UPDATE:'no_update',THROTTLED:'throttled',UPDATE_AVAILABLE:'update_available'},
                        connect: () => ({ onDisconnect:{addListener:()=>{}}, onMessage:{addListener:()=>{}}, postMessage:()=>{} }),
                        sendMessage: () => {},
                        id: undefined,
                        getManifest: () => ({}),
                        getURL: (path) => path,
                        getPlatformInfo: (cb) => cb && cb({os: 'win', arch: 'x86-64', nacl_arch: 'x86-64'})
                    },
                    csi: () => ({ pageT: Date.now(), startE: Date.now(), onloadT: Date.now() }),
                    loadTimes: () => ({
                        commitLoadTime: Date.now()/1000, connectionInfo:'h2', finishDocumentLoadTime: Date.now()/1000,
                        finishLoadTime: Date.now()/1000, firstPaintAfterLoadTime:0, firstPaintTime: Date.now()/1000,
                        navigationType:'navigate', npnNegotiatedProtocol:'h2', requestTime: Date.now()/1000,
                        startLoadTime: Date.now()/1000, wasAlternateProtocolAvailable:false, wasFetchedViaSpdy:true, wasNpnNegotiated:true
                    })
                };
                
                // WebGL spoofing
                const spoofWebGL = (ctx) => {
                    if (!ctx) return;
                    const orig = ctx.prototype.getParameter;
                    ctx.prototype.getParameter = function(p) {
                        if (p === 37445) return 'Google Inc. (NVIDIA)';
                        if (p === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                        if (p === 7936) return 'WebKit';
                        if (p === 7937) return 'WebKit WebGL';
                        return orig.call(this, p);
                    };
                };
                spoofWebGL(WebGLRenderingContext);
                if (typeof WebGL2RenderingContext !== 'undefined') spoofWebGL(WebGL2RenderingContext);
                
                // Canvas fingerprint protection
                const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(type) {
                    const ctx = this.getContext('2d');
                    if (ctx) {
                        const imgData = ctx.getImageData(0, 0, this.width, this.height);
                        for (let i = 0; i < imgData.data.length; i += 4) {
                            imgData.data[i] ^= 1;
                        }
                        ctx.putImageData(imgData, 0, 0);
                    }
                    return origToDataURL.apply(this, arguments);
                };
                
                // Permissions API fix
                if (navigator.permissions) {
                    const origQuery = navigator.permissions.query;
                    navigator.permissions.query = (params) => {
                        if (params.name === 'notifications') {
                            return Promise.resolve({ state: Notification.permission || 'prompt', onchange: null });
                        }
                        return origQuery.call(navigator.permissions, params);
                    };
                }
                
                // Screen properties
                Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
                Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
                
                // AudioContext fingerprint protection
                if (window.AudioContext || window.webkitAudioContext) {
                    const AC = window.AudioContext || window.webkitAudioContext;
                    const origCreateAnalyser = AC.prototype.createAnalyser;
                    AC.prototype.createAnalyser = function() {
                        const analyser = origCreateAnalyser.call(this);
                        const origGetFloatFrequencyData = analyser.getFloatFrequencyData;
                        analyser.getFloatFrequencyData = function(array) {
                            origGetFloatFrequencyData.call(this, array);
                            for (let i = 0; i < array.length; i++) {
                                array[i] += Math.random() * 0.0001;
                            }
                        };
                        return analyser;
                    };
                }
                
                // Connection API
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({
                        effectiveType: '4g',
                        rtt: 50,
                        downlink: 10,
                        saveData: false,
                        onchange: null,
                        addEventListener: () => {},
                        removeEventListener: () => {}
                    })
                });
                
                // Cloudflare Turnstile iframe fix
                const enableIframeClicks = () => {
                    document.querySelectorAll('iframe').forEach(iframe => {
                        iframe.style.pointerEvents = 'auto';
                        try {
                            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                            if (iframeDoc) {
                                iframeDoc.body.style.pointerEvents = 'auto';
                            }
                        } catch(e) {}
                    });
                };
                
                setInterval(enableIframeClicks, 500);
                document.addEventListener('DOMContentLoaded', enableIframeClicks);
                
                console.log('[GBrowser] Anti-detection script loaded successfully');
            })();
        """)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(True)
        self.profile.scripts().insert(script)

        self.browser = QWebEngineView()
        page = CustomWebPage(self.profile, self.browser)
        self.browser.setPage(page)
        
        last_url = self.config.get("last_url", "https://www.google.com")
        self.browser.setUrl(QUrl(last_url))

        # Nav icons
        back_svg = '<svg width="24" height="24"><path d="M20 11 H7.83 l5.59-5.59 L12 4 l-8 8 8 8 1.41-1.41 L7.83 13 H20 v-2 z" fill="#ccc"/></svg>'
        forward_svg = '<svg width="24" height="24"><path d="M12 4 l-1.41 1.41 L16.17 11 H4 v2 h12.17 l-5.58 5.59 L12 20 l8-8 z" fill="#ccc"/></svg>'
        reload_svg = '<svg width="24" height="24"><path d="M17.65 6.35 C16.2 4.9 14.21 4 12 4 c-4.42 0-7.99 3.58-7.99 8 s3.57 8 7.99 8 c3.73 0 6.84-2.55 7.73-6 h-2.08 c-.82 2.33-3.04 4-5.65 4 -3.31 0-6-2.69-6-6 s2.69-6 6-6 c1.66 0 3.14.69 4.22 1.78 L13 11 h7 V4 l-2.35 2.35 z" fill="#ccc"/></svg>'
        home_svg = '<svg width="24" height="24"><path d="M10 20 v-6 h4 v6 h5 v-8 h3 L12 3 2 12 h3 v8 z" fill="#ccc"/></svg>'

        for svg, func in zip([back_svg, forward_svg, reload_svg, home_svg],
                             [self.browser.back, self.browser.forward, self.browser.reload,
                              lambda: self.browser.setUrl(QUrl("https://www.google.com"))]):
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

        self.browser.urlChanged.connect(lambda u: self.url_bar.setText(u.toString()))
        self.browser.page().profile().downloadRequested.connect(self.handle_download)

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
        layout.addWidget(self.browser, 1)

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
        
        self.config["last_url"] = self.browser.url().toString()
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
            print("[DEBUG] Using html5lib parser")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")
            print("[DEBUG] Using html.parser (html5lib not available)")
        
        print(f"[DEBUG] Found top-level DL: {soup.find('dl') is not None}")
        
        def parse_dl(dl_tag, depth=0):
            """Robust recursive parser for Netscape-style bookmarks HTML."""
            nodes = []
            indent = "  " * depth
            
            all_dts = dl_tag.find_all("dt")
            direct_dts = []
            for dt in all_dts:
                parent = dt.parent
                while parent and parent.name != "dl":
                    parent = parent.parent
                if parent is dl_tag:
                    direct_dts.append(dt)
            
            print(f"[DEBUG] {indent}parse_dl: found {len(direct_dts)} direct DT children")
            
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
                        print(f"[DEBUG] {indent}Link: {title[:50]}")
                        nodes.append({"type": "link", "title": title or href, "href": href})
                    continue

                if h3:
                    folder_title = (h3.get_text(strip=True) or "Folder").strip()
                    children = []

                    sibling = dt.next_sibling
                    while sibling:
                        if hasattr(sibling, 'name'):
                            if sibling.name == "dl":
                                print(f"[DEBUG] {indent}Folder '{folder_title}' - found sibling DL")
                                children = parse_dl(sibling, depth + 1)
                                break
                            elif sibling.name == "dt":
                                print(f"[DEBUG] {indent}Folder '{folder_title}' - no sibling DL (hit next DT)")
                                break
                        sibling = sibling.next_sibling
                    
                    if not children:
                        child_dl = dt.find("dl")
                        if child_dl:
                            print(f"[DEBUG] {indent}Folder '{folder_title}' - found nested DL inside DT")
                            children = parse_dl(child_dl, depth + 1)
                    
                    print(f"[DEBUG] {indent}Folder: {folder_title}, children: {len(children)}")
                    nodes.append({"type": "folder", "title": folder_title, "children": children})

            return nodes

        top_dl = soup.find("dl")
        if top_dl:
            parsed = parse_dl(top_dl)
            print(f"[DEBUG] Total parsed items: {len(parsed)}")
            if len(parsed) == 1 and parsed[0].get("type") == "folder":
                print(f"[DEBUG] Unwrapping top-level folder: {parsed[0].get('title')}")
                parsed = parsed[0].get("children", parsed)
        else:
            print("[DEBUG] No DL structure found, falling back to anchor collection")
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
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)  # PyQt6 enum
            self.bookmarks_container_layout.addWidget(spacer)
            return

        for node in self.bookmarks:
            if node["type"] == "link":
                btn = QPushButton(node.get("title", node.get("href", "untitled")))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)  # PyQt6 enum
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
                tb.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)  # PyQt6 enum
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
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)  # PyQt6 enum
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
        self.browser.setUrl(QUrl(href))

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
            if isinstance(w, QWidget) and w.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding:  # PyQt6 enum
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
        menu.exec(self.overflow_btn.mapToGlobal(self.overflow_btn.rect().bottomLeft()))  # PyQt6: exec_ -> exec

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
        self.browser.setUrl(QUrl(url))

    def handle_download(self, item):
        path, _ = QFileDialog.getSaveFileName(self, "Save File", item.suggestedFileName())
        if path:
            item.setDownloadDirectory(os.path.dirname(path))  # PyQt6 API
            item.setDownloadFileName(os.path.basename(path))  # PyQt6 API
            item.accept()

    def closeEvent(self, event):
        self._save_config()
        
        self.browser.stop()
        self.browser.load(QUrl("about:blank"))
        super().closeEvent(event)


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Gorstak's Browser")
        win = Browser()
        win.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        input("Press Enter to exit...")
