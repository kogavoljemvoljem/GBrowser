# Gorstak's Browser - FINAL & EXACTLY AS YOU WANT IT (Native title bar + draggable!)
import os
import sys

# Critical WebEngine fixes
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox"

try:
    import site
    for p in site.getsitepackages():
        qt_bin = os.path.join(p, "PyQt5", "Qt5", "bin")
        if os.path.isdir(qt_bin):
            os.environ["PATH"] = qt_bin + os.pathsep + os.environ["PATH"]
            os.environ["QTWEBENGINE_PROCESS_PATH"] = os.path.join(qt_bin, "QtWebEngineProcess.exe")
except:
    pass

from PyQt5.QtWidgets import *
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, QUrl, QSize
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import QByteArray


class Browser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gorstak's Browser")  # ← Shows in native title bar
        self.setGeometry(100, 100, 1280, 800)
        self.setMinimumSize(800, 600)

        # Native window frame = perfect dragging, resize, min/max/close
        self.setWindowFlags(Qt.Window)

        central = QWidget()
        central.setStyleSheet("background:#1e1e1e;")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === CUSTOM NAVIGATION BAR (below native title bar) ===
        nav = QWidget()
        nav.setFixedHeight(64)
        nav.setStyleSheet("background:#252526;")
        nlay = QHBoxLayout(nav)
        nlay.setContentsMargins(12, 8, 12, 8)
        nlay.setSpacing(12)

        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl("https://www.google.com"))

        # SVG Icon helper
        def svg_icon(svg):
            r = QSvgRenderer(QByteArray(svg.encode()))
            pix = QPixmap(24, 24)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            r.render(p)
            p.end()
            return QIcon(pix)

        back_svg     = '<svg width="24" height="24"><path d="M20 11 H7.83 l5.59-5.59 L12 4 l-8 8 8 8 1.41-1.41 L7.83 13 H20 v-2 z" fill="#ccc"/></svg>'
        forward_svg  = '<svg width="24" height="24"><path d="M12 4 l-1.41 1.41 L16.17 11 H4 v2 h12.17 l-5.58 5.59 L12 20 l8-8 z" fill="#ccc"/></svg>'
        reload_svg   = '<svg width="24" height="24"><path d="M17.65 6.35 C16.2 4.9 14.21 4 12 4 c-4.42 0-7.99 3.58-7.99 8 s3.57 8 7.99 8 c3.73 0 6.84-2.55 7.73-6 h-2.08 c-.82 2.33-3.04 4-5.65 4 -3.31 0-6-2.69-6-6 s2.69-6 6-6 c1.66 0 3.14.69 4.22 1.78 L13 11 h7 V4 l-2.35 2.35 z" fill="#ccc"/></svg>'
        home_svg     = '<svg width="24" height="24"><path d="M10 20 v-6 h4 v6 h5 v-8 h3 L12 3 2 12 h3 v8 z" fill="#ccc"/></svg>'

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

        # Downloads
        self.browser.page().profile().downloadRequested.connect(self.handle_download)

        layout.addWidget(nav)
        layout.addWidget(self.browser, 1)

    def navigate(self):
        url = self.url_bar.text().strip()
        if not url: return
        if " " in url and "." not in url:
            url = "https://www.google.com/search?q=" + url.replace(" ", "+")
        elif not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.browser.setUrl(QUrl(url))

    def handle_download(self, download):
        suggested_name = download.suggestedFileName() if hasattr(download, 'suggestedFileName') else "download"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save File", suggested_name)
        if file_path:
            download.setPath(file_path)
            download.accept()

    def closeEvent(self, event):
        self.browser.stop()
        self.browser.load(QUrl("about:blank"))
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Gorstak's Browser")
    win = Browser()
    win.show()
    sys.exit(app.exec_())
