import sys
import os
import time
import json
import numpy as np
import cv2
import pyautogui
import mss
import traceback
from PyQt6 import QtWidgets, QtCore, QtGui

try:
    import win32gui
    import win32con
    import win32api
except ImportError as e:
    sys.exit(1)

pyautogui.FAILSAFE = True

SETTINGS_FILE = "clicker_settings.json"

TRANSLATIONS = {
    "EN": {
        "title": "Auto Click Simple 29.1.fix",
        "target_imgs": "Target Images",
        "add_img": "Add Image",
        "clear_all": "Clear All",
        "log": "Execution Log",
        "target_group": "TARGET",
        "region_mode": "Region",
        "window_mode": "Window",
        "select_area": "Select Area",
        "select_sub": "Select Sub-Region",
        "rect_full": "Rect: Full Screen",
        "refresh": "Refresh",
        "settings_group": "SETTINGS",
        "mode": "Mode:",
        "multi_click": "Multi-Click",
        "show_vision": "Show Vision",
        "start": "START BOT",
        "stop": "STOP",
        "ready": "Ready",
        "stopped": "Stopped",
        "running": "Running...",
        "about": "About Author",
        "lang": "Language:"
    },
    "RU": {
        "title": "Auto Click Simple 29.1.fix",
        "target_imgs": "Цели (Картинки)",
        "add_img": "Добавить",
        "clear_all": "Очистить",
        "log": "Лог работы",
        "target_group": "ОБЛАСТЬ ПОИСКА",
        "region_mode": "Экран",
        "window_mode": "Окно",
        "select_area": "Выбрать зону",
        "select_sub": "Выбрать под-зону",
        "rect_full": "Зона: Весь экран",
        "refresh": "Обновить",
        "settings_group": "НАСТРОЙКИ",
        "mode": "Режим:",
        "multi_click": "Мульти-клик",
        "show_vision": "Показывать зрение",
        "start": "ЗАПУСТИТЬ",
        "stop": "ОСТАНОВИТЬ",
        "ready": "Готов к работе",
        "stopped": "Остановлен",
        "running": "Работает...",
        "about": "Об авторе",
        "lang": "Язык:"
    }
}

class Signals(QtCore.QObject):
    log = QtCore.pyqtSignal(str)
    started = QtCore.pyqtSignal()
    stopped = QtCore.pyqtSignal()
    match_found = QtCore.pyqtSignal(str, int, int)
    debug_frame = QtCore.pyqtSignal(object)

class WindowUtils:
    @staticmethod
    def get_window_list():
        wins = []
        try:
            def enum_cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                    try:
                        rect = win32gui.GetWindowRect(hwnd)
                        w = rect[2] - rect[0]
                        h = rect[3] - rect[1]
                        if w > 0 and h > 0:
                            wins.append((hwnd, win32gui.GetWindowText(hwnd)))
                    except: pass
            win32gui.EnumWindows(enum_cb, None)
        except Exception as e:
            pass
        return sorted(wins, key=lambda x: x[1])

    @staticmethod
    def get_window_rect(hwnd):
        try:
            rect = win32gui.GetWindowRect(hwnd)
            return rect
        except:
            return None

    @staticmethod
    def background_click(hwnd, x_screen, y_screen):
        try:
            point = win32gui.ScreenToClient(hwnd, (x_screen, y_screen))
            lparam = win32api.MAKELONG(point[0], point[1])
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
        except Exception:
            pass

class ClickerWorker(QtCore.QThread):
    def __init__(self, config, templates, signals):
        super().__init__()
        self.config = config
        self.templates = templates
        self.signals = signals
        self._is_running = True
        self.last_click_time = 0

    def update_config(self, key, value):
        self.config[key] = value

    def run(self):
        self.signals.log.emit(f"Worker started. Mode: {self.config.get('mode')}")
        self.signals.started.emit()
        
        target_hwnd = self.config.get('target_hwnd', 0)
        use_window = self.config.get('use_window', False) and target_hwnd != 0

        with mss.mss() as sct:
            while self._is_running:
                loop_start = time.time()
                try:
                    monitor = {}
                    current_rect = None
                    monitor_offset = (0, 0)
                    
                    if use_window:
                        if win32gui.IsIconic(target_hwnd):
                             time.sleep(1)
                             continue

                        rect = WindowUtils.get_window_rect(target_hwnd)
                        if not rect:
                            self.signals.log.emit("Target window lost or closed.")
                            break
                        
                        rel_Region = self.config.get("relative_region")
                        if rel_Region:
                             abs_x = rect[0] + rel_Region[0]
                             abs_y = rect[1] + rel_Region[1]
                             w = rel_Region[2]
                             h = rel_Region[3]
                             current_rect = (abs_x, abs_y, w, h)
                        else:
                             current_rect = (rect[0], rect[1], rect[2]-rect[0], rect[3]-rect[1])
                    else:
                        current_rect = self.config.get('region')

                    if current_rect:
                        vx = win32api.GetSystemMetrics(76)
                        vy = win32api.GetSystemMetrics(77)
                        vw = win32api.GetSystemMetrics(78)
                        vh = win32api.GetSystemMetrics(79)
                        
                        rx, ry, rw, rh = current_rect
                        
                        x1 = max(vx, rx)
                        y1 = max(vy, ry)
                        x2 = min(vx + vw, rx + rw)
                        y2 = min(vy + vh, ry + rh)
                        
                        w_new = int(x2 - x1)
                        h_new = int(y2 - y1)
                        
                        if w_new <= 0 or h_new <= 0:
                            time.sleep(0.1)
                            continue
                            
                        monitor = {
                            "left": int(x1),
                            "top": int(y1),
                            "width": w_new,
                            "height": h_new
                        }
                        monitor_offset = (int(x1), int(y1))

                    if not monitor:
                        time.sleep(0.1)
                        continue

                    sct_img = sct.grab(monitor)
                    img_np = np.array(sct_img)
                    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
                    
                    found_click_this_frame = False

                    for templ in self.templates:
                        if not self._is_running: break
                        if not self.config.get('multi_click') and found_click_this_frame: break

                        if not templ.get('enabled', True):
                            continue

                        template_img = templ['data']
                        h, w = template_img.shape[:2]

                        res = cv2.matchTemplate(img_bgr, template_img, cv2.TM_CCOEFF_NORMED)
                        threshold = self.config.get('confidence', 0.8)
                        
                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                        
                        if self.config.get('debug', False) and templ.get('enabled', True):
                            top_left = max_loc
                            bottom_right = (top_left[0] + w, top_left[1] + h)
                            color = (0, 0, 255) 
                            if max_val >= threshold:
                                color = (0, 255, 0)
                            
                            cv2.rectangle(img_bgr, top_left, bottom_right, color, 2)
                            cv2.putText(img_bgr, f"{max_val:.2f}", (top_left[0], top_left[1]-5), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

                        if max_val >= threshold:
                            can_click = True
                            if not self.config.get('multi_click') and found_click_this_frame:
                                can_click = False
                            
                            if can_click:
                                now = time.time()
                                if now - self.last_click_time >= self.config.get('interval', 1.0):
                                    match_cx = max_loc[0] + w // 2
                                    match_cy = max_loc[1] + h // 2
                                    
                                    final_x = monitor_offset[0] + match_cx
                                    final_y = monitor_offset[1] + match_cy
                                    
                                    self.signals.match_found.emit(templ['name'], final_x, final_y)
                                    self.signals.log.emit(f"Click: {templ['name']} ({max_val:.2f})")

                                    mode = self.config.get('click_mode', 'Mouse')
                                    if mode == 'Background' and use_window and target_hwnd:
                                        WindowUtils.background_click(target_hwnd, final_x, final_y)
                                    else:
                                        pyautogui.click(x=final_x, y=final_y)
                                    
                                    self.last_click_time = now
                                    found_click_this_frame = True

                    if self.config.get('debug', False):
                        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                        ih, iw, ch = img_rgb.shape
                        qimg = QtGui.QImage(img_rgb.data, iw, ih, ch * iw, QtGui.QImage.Format.Format_RGB888)
                        self.signals.debug_frame.emit(qimg.copy())

                except Exception as e:
                    self.signals.log.emit(f"Error: {e}")
                    time.sleep(1)
                
                elapsed = time.time() - loop_start
                if elapsed < 0.033:
                    time.sleep(0.033 - elapsed)

        self.signals.stopped.emit()

    def stop(self):
        self._is_running = False

class RegionSelector(QtWidgets.QWidget):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.WindowStaysOnTopHint | QtCore.Qt.WindowType.Tool)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.start_point = None
        self.selection = QtCore.QRect()
        
        full_rect = QtCore.QRect()
        for screen in QtWidgets.QApplication.screens():
            full_rect = full_rect.united(screen.geometry())
        self.setGeometry(full_rect)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setBrush(QtGui.QColor(0, 0, 0, 100))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())

        if not self.selection.isNull():
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Clear)
            painter.drawRect(self.selection)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 0, 0), 2))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(self.selection)

    def mousePressEvent(self, event):
        self.start_point = event.pos()
        self.selection = QtCore.QRect()
        self.update()

    def mouseMoveEvent(self, event):
        if self.start_point:
            self.selection = QtCore.QRect(self.start_point, event.pos()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        self.callback(self.selection)
        self.close()

class DebugWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bot Vision")
        self.resize(600, 400)
        self.lbl = QtWidgets.QLabel()
        self.lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.lbl)

    def update_frame(self, qimg):
        pix = QtGui.QPixmap.fromImage(qimg)
        if pix.width() > self.lbl.width() or pix.height() > self.lbl.height():
            pix = pix.scaled(self.lbl.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.lbl.setPixmap(pix)

class AutoClickerApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoClicker Pro")
        self.resize(900, 650)
        
        if os.path.exists("icon.png"):
             self.setWindowIcon(QtGui.QIcon("icon.png"))
        
        self.settings = {}
        self.templates = []
        self.worker = None
        self.debug_win = None
        self.lang = "EN"
        self.load_settings()
        self._init_ui()

    def _init_ui(self):
        self._set_theme()
        
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(10)
        
        self.lbl_imgs = QtWidgets.QLabel()
        self.lbl_imgs.setStyleSheet("font-size: 16px; font-weight: bold; color: #ddd;")
        
        self.list_imgs = QtWidgets.QListWidget()
        self.list_imgs.setIconSize(QtCore.QSize(48, 48))
        self.list_imgs.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_imgs.customContextMenuRequested.connect(self._img_context_menu)
        self.list_imgs.itemChanged.connect(self._item_changed)
        
        img_toolbar = QtWidgets.QHBoxLayout()
        self.btn_add_img = QtWidgets.QPushButton()
        self.btn_add_img.clicked.connect(self._add_image)
        self.btn_clear_imgs = QtWidgets.QPushButton()
        self.btn_clear_imgs.clicked.connect(self._clear_images)
        
        img_toolbar.addWidget(self.btn_add_img)
        img_toolbar.addStretch()
        img_toolbar.addWidget(self.btn_clear_imgs)
        
        self.lbl_log = QtWidgets.QLabel()
        self.lbl_log.setStyleSheet("font-weight: bold; color: #888; margin-top: 10px;")
        
        self.txt_log = QtWidgets.QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #1e1e1e; font-family: Consolas; font-size: 11px;")
        
        left_layout.addWidget(self.lbl_imgs) 
        left_layout.addWidget(self.list_imgs, 75)
        left_layout.addLayout(img_toolbar)
        left_layout.addWidget(self.lbl_log)
        left_layout.addWidget(self.txt_log, 25)
        
        sidebar = QtWidgets.QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        side_layout = QtWidgets.QVBoxLayout(sidebar)
        side_layout.setContentsMargins(15, 15, 15, 15)
        side_layout.setSpacing(20)
        
        self.grp_target = QtWidgets.QGroupBox()
        v_target = QtWidgets.QVBoxLayout()
        v_target.setSpacing(8)
        
        self.rdo_region = QtWidgets.QRadioButton()
        self.rdo_window = QtWidgets.QRadioButton()
        
        self.btn_select_region = QtWidgets.QPushButton()
        self.btn_select_region.clicked.connect(self._pick_region)
        self.lbl_region_info = QtWidgets.QLabel()
        self.lbl_region_info.setStyleSheet("color: #777; font-size: 11px;")
        
        self.cbo_windows = QtWidgets.QComboBox()
        self.btn_refresh_win = QtWidgets.QPushButton()
        self.btn_refresh_win.clicked.connect(self._refresh_windows)
        
        v_target.addWidget(self.rdo_region)
        v_target.addWidget(self.btn_select_region)
        v_target.addWidget(self.lbl_region_info)
        v_target.addSpacing(5)
        v_target.addWidget(self.rdo_window)
        v_target.addWidget(self.cbo_windows)
        v_target.addWidget(self.btn_refresh_win)
        self.grp_target.setLayout(v_target)
        
        self.grp_sett = QtWidgets.QGroupBox()
        v_sett = QtWidgets.QVBoxLayout()
        v_sett.setSpacing(10)
        
        self.spin_conf = QtWidgets.QDoubleSpinBox()
        self.spin_conf.setRange(0.1, 1.0)
        self.spin_conf.setSingleStep(0.05)
        self.spin_conf.setPrefix("Conf: ")
        
        self.spin_interval = QtWidgets.QDoubleSpinBox()
        self.spin_interval.setRange(0.0, 60.0)
        self.spin_interval.setSingleStep(0.1)
        self.spin_interval.setPrefix("Int: ")
        self.spin_interval.setSuffix("s")
        
        self.lbl_mode = QtWidgets.QLabel()
        self.cbo_mode = QtWidgets.QComboBox()
        self.cbo_mode.addItems(["Mouse Click", "Background Click"])
        
        self.chk_multi = QtWidgets.QCheckBox()
        self.chk_debug = QtWidgets.QCheckBox()
        
        h_lang = QtWidgets.QHBoxLayout()
        self.lbl_lang = QtWidgets.QLabel()
        self.cbo_lang = QtWidgets.QComboBox()
        self.cbo_lang.addItems(["EN", "RU"])
        self.cbo_lang.currentTextChanged.connect(self._change_lang)
        h_lang.addWidget(self.lbl_lang)
        h_lang.addWidget(self.cbo_lang)

        v_sett.addWidget(self.spin_conf)
        v_sett.addWidget(self.spin_interval)
        v_sett.addWidget(self.lbl_mode)
        v_sett.addWidget(self.cbo_mode)
        v_sett.addWidget(self.chk_multi)
        v_sett.addWidget(self.chk_debug)
        v_sett.addLayout(h_lang)
        self.grp_sett.setLayout(v_sett)
        
        side_layout.addWidget(self.grp_target)
        side_layout.addWidget(self.grp_sett)
        side_layout.addStretch()
        
        self.lbl_status = QtWidgets.QLabel()
        self.lbl_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #666; font-weight: bold;")
        
        self.btn_start = QtWidgets.QPushButton()
        self.btn_start.setMinimumHeight(45)
        self.btn_start.setObjectName("btnStart")
        self.btn_start.clicked.connect(self._toggle_start)
        
        self.btn_about = QtWidgets.QPushButton()
        self.btn_about.clicked.connect(self._show_about)
        
        side_layout.addWidget(self.lbl_status)
        side_layout.addWidget(self.btn_start)
        side_layout.addWidget(self.btn_about)

        main_layout.addWidget(left_panel, 2)
        main_layout.addWidget(sidebar, 0)
        
        self.rdo_region.toggled.connect(self._update_target_ui)
        self.rdo_window.toggled.connect(self._update_target_ui)
        self.chk_debug.toggled.connect(self._toggle_debug_win)

        self._apply_settings()
        self._update_ui_text()

        self.chk_multi.toggled.connect(self._update_worker_multi)

    def _set_theme(self):
        bg_style = ""
        if os.path.exists("bg.png"):
             path_to_bg = os.path.abspath("bg.png").replace("\\", "/")
             bg_style = f"background-image: url({path_to_bg}); background-position: center; background-repeat: no-repeat;"
             
        style = f"""
        QMainWindow {{ 
            background-color: #121212; 
            {bg_style}
        }}
        
        QWidget#sidebar {{ 
            background-color: rgba(30, 30, 30, 0.95); 
            border-left: 1px solid #333;
        }}

        QWidget {{ color: #d4d4d4; font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
        
        QGroupBox {{ 
            border: none;
            background-color: #252526; 
            border-radius: 6px; 
            margin-top: 22px; 
            font-weight: bold; 
            color: #ccc;
        }}
        QGroupBox::title {{ 
            subcontrol-origin: margin; 
            subcontrol-position: top left; 
            padding: 0 0px; 
            left: 0px; 
            top: 0px;
        }}
        
        QPushButton {{ background-color: #333; border: none; border-radius: 4px; padding: 6px; color: #eee;}}
        QPushButton:hover {{ background-color: #444; }}
        QPushButton:pressed {{ background-color: #007acc; }}
        
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{ 
            background-color: #2d2d30; 
            border: 1px solid #3e3e42; 
            border-radius: 3px; 
            padding: 4px; 
        }}
        
        QListWidget {{
            background-color: rgba(30,30,30,0.8);
            border: 1px solid #333;
            border-radius: 6px;
        }}
        QListWidget::item {{ padding: 8px; }}
        QListWidget::item:selected {{ background-color: #37373d; border-left: 3px solid #007acc; }}

        QPushButton#btnStart {{ 
            background-color: #1b5e20; 
            color: white; 
            font-size: 15px; 
            font-weight: bold; 
            border-radius: 6px;
        }}
        QPushButton#btnStart:hover {{ background-color: #2e7d32; }}
        """
        QtWidgets.QApplication.instance().setStyleSheet(style)

    def _change_lang(self, text):
        self.lang = text
        self._update_ui_text()

    def _update_ui_text(self):
        t = TRANSLATIONS.get(self.lang, TRANSLATIONS["EN"])
        self.setWindowTitle(t["title"])
        self.lbl_imgs.setText(t["target_imgs"])
        self.btn_add_img.setText(t["add_img"])
        self.btn_clear_imgs.setText(t["clear_all"])
        self.lbl_log.setText(t["log"])
        
        self.grp_target.setTitle(t["target_group"])
        self.rdo_region.setText(t["region_mode"])
        self.rdo_window.setText(t["window_mode"])
        
        if self.rdo_region.isChecked():
            self.btn_select_region.setText(t["select_area"])
        else:
            self.btn_select_region.setText(t["select_sub"])
            
        self.btn_refresh_win.setText(t["refresh"])
        
        self.grp_sett.setTitle(t["settings_group"])
        self.lbl_mode.setText(t["mode"])
        self.chk_multi.setText(t["multi_click"])
        self.chk_debug.setText(t["show_vision"])
        self.lbl_lang.setText(t["lang"])
        
        if self.worker:
            self.btn_start.setText(t["stop"])
            self.lbl_status.setText(t["running"])
        else:
            self.btn_start.setText(t["start"])
            self.lbl_status.setText(t["ready"] if self.templates else t["stopped"])
            
        self.btn_about.setText(t["about"])

    def _show_about(self):
        QtWidgets.QMessageBox.information(
            self, 
            "About", 
            "Auto Click Simple v29.1.fix\n\nGitHub: faliseven\n\nCreated for fast and reliable automation."
        )

    def _item_changed(self, item):
        row = self.list_imgs.row(item)
        if 0 <= row < len(self.templates):
            is_checked = (item.checkState() == QtCore.Qt.CheckState.Checked)
            self.templates[row]['enabled'] = is_checked

    def _update_target_ui(self):
        is_region = self.rdo_region.isChecked()
        self.btn_select_region.setEnabled(True) 
        
        self.lbl_region_info.setEnabled(True)
        self.cbo_windows.setEnabled(not is_region)
        self.btn_refresh_win.setEnabled(not is_region)
        
        t = TRANSLATIONS.get(self.lang, TRANSLATIONS["EN"])
        
        if is_region:
            self.cbo_mode.setCurrentText("Mouse Click")
            self.cbo_mode.setEnabled(False)
            self.btn_select_region.setText(t["select_area"])
        else:
            self.cbo_mode.setEnabled(True)
            self.btn_select_region.setText(t["select_sub"])

    def _refresh_windows(self):
        cur_text = self.cbo_windows.currentText()
        self.cbo_windows.clear()
        self.win_list = WindowUtils.get_window_list()
        for h, title in self.win_list:
            self.cbo_windows.addItem(title, h)
        idx = self.cbo_windows.findText(cur_text)
        if idx >= 0: self.cbo_windows.setCurrentIndex(idx)

    def _pick_region(self):
        self.selector = RegionSelector(self._set_region)
        self.selector.show()

    def _set_region(self, rect):
        if not rect.isNull():
            scale = QtWidgets.QApplication.primaryScreen().devicePixelRatio()
            x = int(rect.x() * scale)
            y = int(rect.y() * scale)
            w = int(rect.width() * scale)
            h = int(rect.height() * scale)
            
            if self.rdo_window.isChecked():
                h_win = self.cbo_windows.currentData()
                win_rect = WindowUtils.get_window_rect(h_win)
                if win_rect:
                    wx, wy = win_rect[0], win_rect[1]
                    rx = x - wx
                    ry = y - wy
                    self.settings["relative_region"] = [rx, ry, w, h]
                    self.lbl_region_info.setText(f"Rel: {rx},{ry} {w}x{h}")
                    self.settings["region"] = None
                else:
                    self.lbl_region_info.setText("Error: Window not found")
            else:
                self.settings["region"] = [x,y,w,h]
                self.settings["relative_region"] = None
                self.lbl_region_info.setText(f"Rect: {x},{y} {w}x{h}")

    def _add_image(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select Images", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        for path in paths:
            if path not in [t['path'] for t in self.templates]:
                self._load_template(path)

    def _load_template(self, path):
        try:
            stream = open(path, "rb")
            bytes = bytearray(stream.read())
            arr = np.asarray(bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                name = os.path.basename(path)
                self.templates.append({"path": path, "name": name, "data": img, "enabled": True})
                
                if img.size > 0:
                   icon_img = cv2.resize(img, (48, 48), interpolation=cv2.INTER_AREA)
                   icon = QtGui.QIcon(QtGui.QPixmap.fromImage(QtGui.QImage(icon_img.data, icon_img.shape[1], icon_img.shape[0], icon_img.strides[0], QtGui.QImage.Format.Format_BGR888)))
                   item = QtWidgets.QListWidgetItem(icon, name)
                   item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                   item.setCheckState(QtCore.Qt.CheckState.Checked)
                   
                   self.list_imgs.addItem(item)
        except Exception as e:
            self._log(f"Error loading {path}: {e}")

    def _clear_images(self):
         self.templates.clear()
         self.list_imgs.clear()

    def _img_context_menu(self, pos):
        item = self.list_imgs.itemAt(pos)
        if item:
            menu = QtWidgets.QMenu()
            act_del = menu.addAction("Remove")
            res = menu.exec(self.list_imgs.mapToGlobal(pos))
            if res == act_del:
                row = self.list_imgs.row(item)
                self.list_imgs.takeItem(row)
                self.templates.pop(row)

    def _log(self, msg):
        self.txt_log.appendPlainText(time.strftime("[%H_%M_%S] ") + msg)

    def _toggle_debug_win(self, checked):
        if checked:
            if not self.debug_win: 
                 self.debug_win = DebugWindow()
            self.debug_win.show()
        else:
            if self.debug_win: self.debug_win.hide()
        
        if self.worker:
            self.worker.update_config("debug", checked)

    def _update_worker_multi(self, checked):
        if self.worker:
            self.worker.update_config("multi_click", checked)

    def _toggle_start(self):
        t = TRANSLATIONS.get(self.lang, TRANSLATIONS["EN"])
        if self.worker:
            self.worker.stop()
            self.worker.wait()
            self.worker = None
            self.btn_start.setText(t["start"])
            self.btn_start.setStyleSheet("background-color: #1b5e20; color: white; font-size: 15px; font-weight: bold; border-radius: 6px;")
            self._enable_controls(True)
            self.lbl_status.setText(t["stopped"])
            self.lbl_status.setStyleSheet("color: #888;")
        else:
            if not self.templates:
                QtWidgets.QMessageBox.warning(self, "No Targets", "Please add at least one image.")
                return

            self._enable_controls(False)
            self.btn_start.setText(t["stop"])
            self.btn_start.setStyleSheet("background-color: #b71c1c; color: white; font-size: 15px; font-weight: bold; border-radius: 6px;")
            self.lbl_status.setText(t["running"])
            self.lbl_status.setStyleSheet("color: #4caf50;")
            
            cfg = {
                "use_window": self.rdo_window.isChecked(),
                "target_hwnd": self.cbo_windows.currentData() if self.rdo_window.isChecked() else 0,
                "region": self.settings.get("region"),
                "relative_region": self.settings.get("relative_region"),
                "confidence": self.spin_conf.value(),
                "interval": self.spin_interval.value(),
                "click_mode": "Background" if "Background" in self.cbo_mode.currentText() else "Mouse",
                "multi_click": self.chk_multi.isChecked(),
                "debug": self.chk_debug.isChecked()
            }
            
            sig = Signals()
            sig.log.connect(self._log)
            sig.debug_frame.connect(lambda qimg: self.debug_win.update_frame(qimg) if self.debug_win and self.debug_win.isVisible() else None)
            
            self.worker = ClickerWorker(cfg, self.templates, sig)
            self.worker.start()

    def _enable_controls(self, enable):
        pass

    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f: self.settings = json.load(f)
        except: self.settings = {}

    def _apply_settings(self):
        s = self.settings
        self.rdo_window.setChecked(s.get("use_window", False))
        self.rdo_region.setChecked(not s.get("use_window", False))
        r = s.get("region")
        if r: self.lbl_region_info.setText(f"Rect: {r[0]},{r[1]} {r[2]}x{r[3]}")
        self.spin_conf.setValue(s.get("confidence", 0.8))
        self.spin_interval.setValue(s.get("interval", 1.0))
        self.chk_multi.setChecked(s.get("multi", False))
        self.chk_debug.setChecked(s.get("debug", False))
        
        self.lang = s.get("lang", "EN")
        self.cbo_lang.setCurrentText(self.lang)
        
        for p in s.get("images", []):
            if os.path.exists(p): self._load_template(p)
        self._refresh_windows()

    def closeEvent(self, event):
        s = self.settings
        s["use_window"] = self.rdo_window.isChecked()
        s["confidence"] = self.spin_conf.value()
        s["interval"] = self.spin_interval.value()
        s["multi"] = self.chk_multi.isChecked()
        s["debug"] = self.chk_debug.isChecked()
        s["lang"] = self.lang
        s["images"] = [t['path'] for t in self.templates]
        try:
            with open(SETTINGS_FILE, "w") as f: json.dump(s, f, indent=2)
        except: pass
        if self.worker:
            self.worker.stop()
            self.worker.wait()
        if self.debug_win: self.debug_win.close()
        super().closeEvent(event)

def main():
    try:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except: 
            pass
            
        app = QtWidgets.QApplication(sys.argv)
        w = AutoClickerApp()
        w.show()
        sys.exit(app.exec())
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
