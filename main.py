import sqlite3
import sys
import re
import os
import json
import faulthandler
import traceback
import threading
faulthandler.enable()  # 當機除錯
import time


from PySide6.QtWidgets import (
    QApplication, QWidget, QListWidget, QLineEdit,
    QTextEdit, QTextBrowser, QPushButton, QComboBox,
    QHBoxLayout, QVBoxLayout, QLayout, QSizePolicy,
    QLabel, QGroupBox, QGridLayout, QFrame, QScrollArea,
    QListWidgetItem, QCheckBox, QInputDialog, QMessageBox,
    QListView, QStyledItemDelegate, QStackedWidget, QStyle,
    QDialog, QToolTip, QAbstractItemView
)
from PySide6.QtCore import (
    Qt, QSize, QTimer, QRect, QPoint,
    QModelIndex, QAbstractListModel, QObject, Signal, QEvent
)
from PySide6.QtGui import (
    QFont, QPixmap, QIcon, QColor, QPainter, QPen, QBrush,
    QPixmapCache, QCursor
)

# ========================= 常數設定 =========================
TYPE_MONSTER = 0x1
TYPE_MAGIC = 0x2
TYPE_TRAP = 0x4
TYPE_TOKEN = 0x4000
TYPE_PENDULUM = 0x1000000
TYPE_LINK = 0x4000000

ATTRIBUTE_MAP = {
    0x1: "地", 0x2: "水", 0x4: "炎", 0x8: "風", 0x10: "光", 0x20: "暗", 0x40: "神"
}

RACE_MAP = {
    0x1: "戰士", 0x2: "魔法師", 0x4: "天使", 0x8: "惡魔", 0x10: "不死",
    0x20: "機械", 0x40: "水", 0x80: "炎", 0x100: "岩石", 0x200: "鳥獸",
    0x400: "植物", 0x800: "昆蟲", 0x1000: "雷", 0x2000: "龍", 0x4000: "獸",
    0x8000: "獸戰士", 0x10000: "恐龍", 0x20000: "魚", 0x40000: "海龍", 0x80000: "爬蟲類",
    0x100000: "念動力", 0x200000: "幻神獸", 0x400000: "創造神", 0x800000: "幻龍", 0x1000000: "電子界", 0x2000000: "幻想魔"
}

TYPE_CHINESE = {
    0x1: "怪獸",0x10: "通常",0x20: "效果",0x40: "融合",
    0x2000: "同步",0x800000: "超量",0x1000000: "靈擺",0x4000000: "連結",0x200: "靈魂",
    0x400: "聯合",0x800: "二重",0x1000: "協調",0x4000: "衍生物",0x200000: "反轉",
    0x400000: "卡通",0x2000000: "特殊召喚",0x2: "魔法",0x10000: "速攻",0x40000: "裝備",
    0x80000: "場地",0x4: "陷阱",0x100000: "反擊",
    0x1000000000000000: "永續魔法",0x2000000000000000: "永續陷阱",
    0x4000000000000000: "儀式怪獸",0x8000000000000000: "儀式魔法",
}

LINK_MARKERS = {(0, 0): 0o1, (1, 0): 0o2, (2, 0): 0o4, (0, 1): 0o10,(2, 1): 0o40, (0, 2): 0o100, (1, 2): 0o200, (2, 2): 0o400}

ARROW_SYMBOLS = {0o1: "↙", 0o2: "↓", 0o4: "↘", 0o10: "←",0o40: "→", 0o100: "↖", 0o200: "↑", 0o400: "↗"}

SETNAME_MAP = {}

CATEGORY_MAP = {
    0x1: "魔陷破壞",0x2: "怪獸破壞",0x4: "卡片除外",0x8: "送去墓地",0x10: "返回手牌",
    0x20: "返回卡組",0x40: "手牌破壞",0x80: "卡組破壞",0x100: "抽卡輔助",0x200: "卡組檢索",
    0x400: "卡片回收",0x800: "表示變更",0x1000: "控制權",0x2000: "攻守變化",0x4000: "貫穿傷害",
    0x8000: "多次攻擊",0x10000: "攻擊限制",0x20000: "直接攻擊",0x40000: "特殊召喚",0x80000: "衍生物",
    0x100000: "種族相關",0x200000: "屬性相關",0x400000: "LP傷害",0x800000: "LP回復",0x1000000: "破壞抗性",
    0x2000000: "效果抗性",0x4000000: "指示物",0x8000000: "賭博相關",0x10000000: "融合相關",0x20000000: "同調相關",
    0x40000000: "超量相關",0x80000000: "效果無效",
}

# 字段
def load_strings_conf():
    global SETNAME_MAP
    SETNAME_MAP.clear()
    conf_path = os.path.join(os.path.dirname(__file__), "strings.conf")
    if not os.path.exists(conf_path):
        return
    pattern = re.compile(r"^!setname\s+(0x[0-9a-fA-F]+)\s+(.+)$")
    try:
        with open(conf_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                match = pattern.match(line)
                if match:
                    code_str, name = match.groups()
                    try:
                        code = int(code_str, 16)
                        SETNAME_MAP[code] = name.strip()
                    except ValueError:
                        continue
    except Exception as e:
        print(f"讀取 strings.conf 失敗: {e}")

# 限制表
class LFLIST:
    def __init__(self):
        self.data = {}
        self.labels = []
        self._load()

    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "lflist.conf")
        if not os.path.exists(path):
            return
        current_labels = []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#") or line.startswith("!"):
                    labels = re.findall(r"\[([^\]]+)\]", line)
                    exclaim_matches = []
                    if line.startswith("!"):
                        rest = line[1:].strip()
                        if '#' in rest:
                            rest = rest.split('#', 1)[0].strip()
                        if rest:
                            exclaim_matches.append(rest)
                    all_labels = labels + exclaim_matches
                    if all_labels:
                        current_labels = all_labels
                        for lab in current_labels:
                            if lab not in self.data:
                                self.data[lab] = {}
                    continue
                if current_labels:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            cid = int(parts[0])
                            limit = int(parts[1])
                            for lab in current_labels:
                                self.data[lab][cid] = limit
                        except ValueError:
                            pass
        self.labels = sorted(self.data.keys(), reverse=True)

    def get_limit(self, cid, label):
        if label in self.data and cid in self.data[label]:
            return self.data[label][cid]
        return 3

    def get_labels(self):
        return self.labels


# Lua 索引快取管理器
class LuaCacheManager:
    def __init__(self):
        self.script_dir = os.path.join(os.path.dirname(__file__), "script")
        self.cache_path = os.path.join(os.path.dirname(__file__), "lua_cache_v2.json")
        self.card_data = {}
        self.last_updated = 0.0
        self.inverted_index = {}
        self.is_loaded = False
        self._lock = threading.Lock()

    def load_or_build(self, all_cids, progress_callback=None, finished_callback=None):
        self.is_loaded = False
        
        def _thread_worker():
            # 1. 嘗試讀取舊有的 JSON 快取
            self._load_cache()
            
            # 2. 與資料夾中的實際 lua 檔案進行增量比對和更新
            self._update_cache(all_cids, progress_callback)
            
            # 3. 建立記憶體中的反向索引
            self._build_inverted_index()
            
            self.is_loaded = True
            if finished_callback:
                QTimer.singleShot(0, finished_callback)

        t = threading.Thread(target=_thread_worker, daemon=True, name="lua-cache-worker")
        t.start()

    def _load_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    with self._lock:
                        self.card_data = data.get("card_data", {})
                        self.last_updated = data.get("last_updated", 0.0)
            except Exception as e:
                print(f"載入 Lua 快取 JSON 失敗: {e}")
                with self._lock:
                    self.card_data = {}
                    self.last_updated = 0.0

    def _update_cache(self, all_cids, progress_callback):
        if not os.path.exists(self.script_dir):
            return

        # 掃描 script 目錄，整理出所有實際存在的 c*.lua 檔案及其修改時間
        try:
            files = os.listdir(self.script_dir)
        except Exception:
            return

        lua_files = {}  # cid -> (filename, mtime)
        for f in files:
            if f.startswith("c") and f.endswith(".lua"):
                try:
                    cid = int(f[1:-4])
                    path = os.path.join(self.script_dir, f)
                    mtime = os.path.getmtime(path)
                    lua_files[cid] = (f, mtime)
                except Exception:
                    continue

        updated = False
        to_parse = []

        # 找出哪些 cid 需要重新解析 (不在快取中，或者 lua 檔案有更新)
        all_cids_set = set(all_cids)
        with self._lock:
            # 刪除在快取中但資料庫已不存在的 card_data
            for cid_str in list(self.card_data.keys()):
                try:
                    cid = int(cid_str)
                except ValueError:
                    cid = None
                if cid is None or cid not in all_cids_set:
                    del self.card_data[cid_str]
                    updated = True

            for cid in all_cids:
                cid_str = str(cid)
                if cid not in lua_files:
                    if cid_str in self.card_data:
                        del self.card_data[cid_str]
                        updated = True
                    continue

                f_name, mtime = lua_files[cid]
                # 如果快取中沒有，或者檔案最後修改時間比快取更新時間新，就重新解析
                if cid_str not in self.card_data or mtime > self.last_updated:
                    to_parse.append((cid, os.path.join(self.script_dir, f_name)))

        if to_parse:
            updated = True
            total = len(to_parse)
            const_pat = re.compile(r'\b[A-Z_]{3,30}\b')

            def parse_one(item):
                cid, path = item
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    consts = set(const_pat.findall(content))
                    if "aux.EnableChangeCode" in content:
                        consts.add("🔁 可改變卡片名稱")
                    if "aux.AddContactFusionProcedure" in content or "Contact_Fusion" in content or "ContactFusion" in content:
                        consts.add("🌀 接觸融合素材")
                    if "Duel.Win" in content:
                        consts.add("🏆 特殊勝利條件")
                    return cid, list(consts)
                except Exception:
                    return cid, []

            from concurrent.futures import ThreadPoolExecutor
            max_workers = min(32, (os.cpu_count() or 4) * 4)
            results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(parse_one, item) for item in to_parse]
                for idx, future in enumerate(futures):
                    if progress_callback and idx % 200 == 0:
                        pct = int((idx / total) * 100)
                        QTimer.singleShot(0, lambda p=pct: progress_callback(p))
                    results.append(future.result())

            with self._lock:
                for cid, consts in results:
                    self.card_data[str(cid)] = consts

        if updated:
            import time
            self.last_updated = time.time()
            try:
                with open(self.cache_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "version": 1,
                        "last_updated": self.last_updated,
                        "card_data": self.card_data
                    }, f, ensure_ascii=False)
            except Exception as e:
                print(f"儲存 Lua 快取 JSON 失敗: {e}")

    def _build_inverted_index(self):
        temp_index = {}
        with self._lock:
            for cid_str, terms in self.card_data.items():
                try:
                    cid = int(cid_str)
                except ValueError:
                    continue
                for term in terms:
                    temp_index.setdefault(term, set()).add(cid)
        self.inverted_index = temp_index

    def get_matching_cids(self, term):
        return self.inverted_index.get(term, set())

# 收藏夾
class FavoritesManager:

    def __init__(self):
        self._path = os.path.join(os.path.dirname(__file__), "favorites.json")
        self._data = {}
        self._current = "預設"
        self.load()

    def load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._data = data
                    else:
                        self._data = {}
            except:
                self._data = {}
        if "預設" not in self._data:
            self._data["預設"] = []
        self._current = "預設"
        self.save()

    def save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_folders(self):
        return list(self._data.keys())

    def get_current(self):
        return self._current

    def set_current(self, name):
        if name in self._data:
            self._current = name

    def add_folder(self, name):
        if name and name not in self._data:
            self._data[name] = []
            self.save()
            return True
        return False

    def remove_folder(self, name):
        if name == "預設":
            return False
        if name in self._data:
            del self._data[name]
            if self._current == name:
                self._current = "預設"
            self.save()
            return True
        return False

    def add_card(self, folder, cid):
        if folder in self._data and cid not in self._data[folder]:
            self._data[folder].append(cid)
            self.save()

    def remove_card(self, folder, cid):
        if folder in self._data and cid in self._data[folder]:
            self._data[folder].remove(cid)
            self.save()

    def contains(self, folder, cid):
        return folder in self._data and cid in self._data[folder]

    def get_cards(self, folder):
        return self._data.get(folder, [])

# QSS 主題
DARK_STYLE = """
QWidget { background-color: #1e1e24; color: #e0e0e6; font-family: "Microsoft JhengHei"; font-size: 12px; }
QGroupBox { border: 1px solid #3a3a42; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #00d2ff; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 3px; }
QLineEdit, QComboBox, QCheckBox { background-color: #2a2a35; border: 1px solid #4a4a5a; border-radius: 4px; padding: 4px; color: white; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left: none; background: transparent; }
QComboBox::down-arrow { image: url("down_arrow.png"); width: 12px; height: 12px; margin-right: 8px; }
QCheckBox { spacing: 5px; }
QListWidget, QListView { background-color: #2a2a35; border: 1px solid #4a4a5a; border-radius: 6px; outline: 0; }
QListWidget::item, QListView::item { border: none; padding: 5px; border-bottom: 1px solid #333340; }
QListWidget::item:selected, QListView::item:selected { background-color: #005f87; color: white; border: none; outline: none; }
QListWidget::item:focus, QListView::item:focus { outline: none; border: none; }
QTextEdit { background-color: #141419; border: 1px solid #3a3a42; border-radius: 6px; padding: 8px; }
QPushButton { background-color: #007acc; color: white; border: none; padding: 5px 10px; border-radius: 3px; }
QPushButton:hover { background-color: #0098ff; }
QPushButton:checked { background-color: #004d7a; color: white; }
QPushButton#reset_btn { background-color: #4e4e5a; color: #ff6b6b; max-width: 24px; max-height: 20px; font-size: 10px; font-weight: bold; }
QPushButton#clear_all_btn { background-color: #e81123; font-weight: bold; color: white; padding: 6px; border-radius: 4px; }
QPushButton#clear_all_btn:hover { background-color: #ff3344; }
QPushButton#link_btn { background-color: #2d2d3a; border: 1px solid #4a4a5a; min-width: 25px; min-height: 25px; }
QPushButton#link_btn:checked { background-color: #004d7a; }
QPushButton:disabled { background-color: #1e1e24; color: #55555d; border: 1px solid #33333d; }
QPushButton#fav_btn { background-color: #2d2d3a; border: 1px solid #888; min-width: 90px; }
QPushButton#fav_btn:checked { background-color: #ffaa00; color: #000; }
QPushButton#wiki_btn, QPushButton#qa_btn, QPushButton#detail_btn { background-color: #2d2d3a; border: 1px solid #888; min-width: 90px; }
QPushButton#wiki_btn:hover, QPushButton#qa_btn:hover, QPushButton#detail_btn:hover { background-color: #3d3d4a; }
QPushButton#folder_btn { background-color: #2d2d3a; border: 1px solid #666; min-width: 24px; max-width: 24px; }
QPushButton#folder_btn:hover { background-color: #4a4a5a; }
QScrollBar:vertical { background-color: #141419; width: 10px; margin: 0; border: none; }
QScrollBar::handle:vertical { background-color: #4e4e5a; min-height: 30px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background-color: #6e6e7a; }
QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical,
QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; border: none; height: 0px; }
QScrollBar:horizontal { background-color: #141419; height: 10px; margin: 0; border: none; }
QScrollBar::handle:horizontal { background-color: #4e4e5a; min-width: 30px; border-radius: 5px; }
QScrollBar::handle:horizontal:hover { background-color: #6e6e7a; }
QScrollBar::sub-line:horizontal, QScrollBar::add-line:horizontal,
QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; border: none; width: 0px; }
"""

# 自動縮放
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self._items = []
        self._stretch = False
        self._stretch_threshold = 0
        self._uniform_last_line = False
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def setStretchItems(self, enabled: bool, threshold: int = 0, uniform_last_line: bool = False):
        self._stretch = enabled
        self._stretch_threshold = threshold
        self._uniform_last_line = uniform_last_line
        self.invalidate()

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margin = self.contentsMargins()
        size += QSize(margin.left() + margin.right(), margin.top() + margin.bottom())
        return size

    def _doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        spacing = self.spacing()
        right = rect.right()

        lines = []
        current_line = []
        for item in self._items:
            widget = item.widget()
            space_h = spacing if spacing >= 0 else widget.style().layoutSpacing(
                QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal
            )
            item_width = item.sizeHint().width()
            needed = item_width + (space_h if current_line else 0)
            if current_line and x + needed > right:
                lines.append(current_line)
                current_line = []
                x = rect.x()
            current_line.append(item)
            x += item_width + space_h
        if current_line:
            lines.append(current_line)

        full_line_item_width = None
        if self._stretch:
            for line in lines:
                if len(line) >= self._stretch_threshold:
                    total_item_width = sum(it.sizeHint().width() for it in line)
                    total_spacing = spacing * (len(line) - 1) if spacing >= 0 else 0
                    extra = right - (rect.x() + total_item_width + total_spacing)
                    if len(line) > 0:
                        full_line_item_width = line[0].sizeHint().width() + extra // len(line)
                    break

        x = rect.x()
        y = rect.y()
        for line in lines:
            item_count = len(line)
            do_stretch = False
            target_item_width = None
            if self._stretch:
                if item_count >= self._stretch_threshold:
                    do_stretch = True
                elif self._uniform_last_line and line is lines[-1] and full_line_item_width is not None:
                    do_stretch = True
                    target_item_width = full_line_item_width

            if do_stretch:
                total_item_width = sum(it.sizeHint().width() for it in line)
                total_spacing = spacing * (item_count - 1) if spacing >= 0 else 0
                extra = right - (x + total_item_width + total_spacing)
                if item_count > 0:
                    if target_item_width is None:
                        per_item_extra = extra // item_count
                        remainder = extra - per_item_extra * item_count
                        for i, item in enumerate(line):
                            item_w = item.sizeHint().width()
                            final_w = item_w + per_item_extra + (remainder if i == item_count - 1 else 0)
                            if not testOnly:
                                item.setGeometry(QRect(x, y, final_w, item.sizeHint().height()))
                            space_h = spacing if spacing >= 0 else item.widget().style().layoutSpacing(
                                QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal
                            )
                            x += final_w + space_h
                    else:
                        for i, item in enumerate(line):
                            final_w = target_item_width
                            if not testOnly:
                                item.setGeometry(QRect(x, y, final_w, item.sizeHint().height()))
                            space_h = spacing if spacing >= 0 else item.widget().style().layoutSpacing(
                                QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal
                            )
                            x += final_w + space_h
            else:
                for i, item in enumerate(line):
                    item_w = item.sizeHint().width()
                    if not testOnly:
                        item.setGeometry(QRect(x, y, item_w, item.sizeHint().height()))
                    space_h = spacing if spacing >= 0 else item.widget().style().layoutSpacing(
                        QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal
                    )
                    x += item_w + space_h

            y += line[0].sizeHint().height() + (spacing if spacing >= 0 else 0)
            x = rect.x()

        return y - rect.y()

# ========================= 三態類型按鈕 =========================
class TriStateButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.state = 0
        self.setCheckable(False)
        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(self._on_long_press)
        self._press_active = False
        self.update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_active = True
            self._long_press_timer.start(300)
        elif event.button() == Qt.RightButton:
            self.on_right_click()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._press_active:
            self._press_active = False
            if self._long_press_timer.isActive():
                self._long_press_timer.stop()
                self.on_left_click()
        super().mouseReleaseEvent(event)

    def _on_long_press(self):
        self._press_active = False
        self.on_right_click()

    def on_left_click(self):
        if self.state == 0:
            self.state = 1
        else:
            self.state = 0
        self.update_style()
        self.window().apply_filter()

    def on_right_click(self):
        if self.state == 0:
            self.state = 2
        else:
            self.state = 0
        self.update_style()
        self.window().apply_filter()

    def update_style(self):
        if self.state == 0:
            self.setStyleSheet("")
        elif self.state == 1:
            self.setStyleSheet("""
                background-color: #004d7a;
                color: white;
                font-weight: bold;
                border: 1px solid #4a4a5a;
            """)
        else:
            self.setStyleSheet("""
                background-color: #e81123;
                color: white;
                font-weight: bold;
                border: 1px solid #4a4a5a;
            """)

    def reset_state(self):
        self.state = 0
        self.update_style()

    def get_state(self):
        return self.state

# ========================= Model / Delegate =========================
class DetailCardModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._lf_label = None
        self._lflist = None

    def set_cards(self, cards):
        self.beginResetModel()
        self._cards = cards
        self.endResetModel()

    def set_lflist_info(self, lflist, label):
        self._lflist = lflist
        self._lf_label = label
        if self._cards:
            self.dataChanged.emit(self.index(0), self.index(self.rowCount()-1), [Qt.UserRole+2])

    def rowCount(self, parent=QModelIndex()):
        return len(self._cards)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._cards):
            return None
        card = self._cards[index.row()]
        if role == Qt.DisplayRole:
            return card[1]
        elif role == Qt.UserRole:
            return card[0]
        elif role == Qt.UserRole + 1:
            return card
        elif role == Qt.UserRole + 2:
            if self._lflist and self._lf_label:
                return self._lflist.get_limit(card[0], self._lf_label)
            return 3
        return None

class DetailCardDelegate(QStyledItemDelegate):
    IMG_SIZE = QSize(80, 110)
    PADDING = 6
    INFO_LEFT = IMG_SIZE.width() + PADDING * 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap_cache = {}

    def paint(self, painter, option, index):
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#005f87"))

        card = index.data(Qt.UserRole + 1)
        if not card:
            painter.restore()
            return

        cid, name, desc, ctype, atk, df, level, race, attr, setcode, alias, ot, category = card
        limit = index.data(Qt.UserRole + 2)

        rect = option.rect
        img_rect = QRect(rect.left() + self.PADDING, rect.top() + self.PADDING,
                         self.IMG_SIZE.width(), self.IMG_SIZE.height())
        pixmap = self._get_pixmap(cid)
        painter.drawPixmap(img_rect, pixmap)
        painter.setPen(QPen(QColor(0x3a, 0x3a, 0x42)))
        painter.drawRect(img_rect)

        if limit is not None and limit != 3:
            colors = {0: QColor(220, 50, 50), 1: QColor(255, 180, 0), 2: QColor(50, 200, 50)}
            color = colors.get(limit, QColor(128,128,128))
            radius = 12
            x = img_rect.left() + 4
            y = img_rect.top() + 4
            painter.setPen(QPen(QColor(40,40,50), 1))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(x, y, radius*2, radius*2)
            painter.setPen(QPen(Qt.white, 1))
            painter.setFont(QFont("Arial", radius, QFont.Bold))
            texts = {0: "禁", 1: "限", 2: "準"}
            painter.drawText(x, y, radius*2, radius*2, Qt.AlignCenter, texts.get(limit, ""))

        text_left = rect.left() + self.INFO_LEFT
        name_top = rect.top() + self.PADDING + 12

        painter.setPen(QColor("#ffffff"))
        name_font = QFont("Microsoft JhengHei", 11, QFont.Bold)
        painter.setFont(name_font)
        painter.drawText(text_left, name_top, name)

        is_monster = bool(ctype & TYPE_MONSTER)
        is_magic = bool(ctype & TYPE_MAGIC)
        is_trap = bool(ctype & TYPE_TRAP)

        if is_monster:
            race_list = [v for k, v in RACE_MAP.items() if race & k]
            race_text = "/".join(race_list) if race_list else ""
            attr_text = ATTRIBUTE_MAP.get(attr, "")
            special_tags = []
            if ctype & TYPE_MONSTER:
                tag_map = {
                    0x80: "儀式", 0x40: "融合", 0x2000: "同步", 0x800000: "超量",
                    0x1000000: "靈擺", 0x4000000: "連結", 0x200: "靈魂", 0x400: "聯合",
                    0x800: "二重", 0x1000: "協調", 0x200000: "反轉", 0x400000: "卡通",
                    0x2000000: "特殊召喚"
                }
                for mask, tag_name in tag_map.items():
                    if ctype & mask:
                        special_tags.append(tag_name)
            parts = []
            if attr_text:
                parts.append(attr_text)
            if race_text:
                parts.append(race_text)
            if special_tags:
                parts.extend(special_tags)
            subtype_str = "/".join(parts) if parts else "?"
            lv = level & 0xFFFF
            if ctype & TYPE_LINK:
                star_str = f"LINK-{level & 0xFF}"
            else:
                star_str = f"★{lv}"
            line2 = f"怪獸({subtype_str}) {star_str}"
        elif is_magic:
            line2 = "魔法"
        elif is_trap:
            line2 = "陷阱"
        else:
            line2 = ""

        line2_top = name_top + 22
        painter.setPen(QColor("#e0e0e6"))
        painter.setFont(QFont("Microsoft JhengHei", 10))
        painter.drawText(text_left, line2_top, line2)

        if is_monster:
            atk_str = '?' if atk == -2 else str(atk)
            def_str = '?' if df == -2 else str(df)
            if ctype & TYPE_LINK:
                stat_str = f"ATK/{atk_str}"
            else:
                stat_str = f"{atk_str}/{def_str}"
            stat_top = line2_top + 22
            painter.setPen(QColor("#e0e0e6"))
            painter.setFont(QFont("Microsoft JhengHei", 10))
            painter.drawText(text_left, stat_top, stat_str)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(0, self.IMG_SIZE.height() + self.PADDING * 2 + 30)

    def _get_pixmap(self, cid):
        if cid in self._pixmap_cache:
            return self._pixmap_cache[cid]
        img_path = os.path.join(os.path.dirname(__file__), "pics", f"{cid}.jpg")
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path).scaled(self.IMG_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            pixmap = QPixmap(self.IMG_SIZE)
            pixmap.fill(QColor(80, 80, 80))
        self._pixmap_cache[cid] = pixmap
        return pixmap

# ========================= YGOPRODeck 詳細數據對話框 =========================
class CardDetailDialog(QDialog):
    def __init__(self, parent_viewer, card_info):
        super().__init__(parent_viewer)
        self.setWindowTitle(f"卡片詳細數據 - {card_info.get('name', '')}")
        self.resize(600, 500)
        self._build_ui(card_info)

    def _build_ui(self, card_info):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        lbl_tip = QLabel("YGOPRODeck API 原始數據:")
        lbl_tip.setStyleSheet("font-weight: bold; color: #00d2ff;")
        layout.addWidget(lbl_tip)

        browser = QTextBrowser(self)
        browser.setFont(QFont("Consolas", 10) if sys.platform == "win32" else QFont("Monospace", 10))
        browser.setStyleSheet("background-color: #141419; border: 1px solid #3a3a42; border-radius: 6px; padding: 8px;")
        
        formatted_json = json.dumps(card_info, indent=4, ensure_ascii=False)
        browser.setPlainText(formatted_json)
        layout.addWidget(browser)

        btn_close = QPushButton("關閉")
        btn_close.clicked.connect(self.close)
        btn_close.setFixedWidth(80)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

# ========================= Lua 常數對話框（優化排版） =========================
class ConstantDialog(QDialog):
    def __init__(self, parent_viewer):
        super().__init__(parent_viewer)
        self.viewer = parent_viewer
        self.setWindowTitle("Lua 腳本常數過濾")
        self.resize(850, 650)
        self.buttons = {}
        # dialog 自己的 timer（有 parent，生命週期安全），debounce 50ms
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(50)
        self._apply_timer.timeout.connect(self._do_apply)
        self._build_ui()

    def _do_apply(self):
        """timer timeout 後才呼叫 apply_filter，避免在 signal handler 裡操作 Qt"""
        try:
            self.viewer.apply_filter()
        except Exception:
            with open("crash_log.txt", "a", encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ---------- 搜尋框 ----------
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜尋常數名稱或說明...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumHeight(28)
        self.search_edit.textChanged.connect(self._filter_buttons)
        main_layout.addWidget(self.search_edit)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)
        container_layout.setContentsMargins(4, 4, 4, 4)

        self._group_widgets = []  # [(group_box, [(name, btn), ...])] for filter
        for group_title, constants in self.viewer.constants_groups:
            if not constants:
                continue
            group_box = QGroupBox(group_title if group_title else "其他")
            group_inner = QVBoxLayout()
            group_inner.setContentsMargins(6, 10, 6, 6)
            group_inner.setSpacing(4)
            flow = FlowLayout(margin=2, spacing=4)
            flow.setStretchItems(True, threshold=4, uniform_last_line=True)
            group_btn_list = []
            for name, hex_str in constants:
                comment = self.viewer.constant_comment_map.get(name, "")
                btn = QPushButton(name)
                btn.setCheckable(True)
                btn.setChecked(self.viewer.constant_buttons_state.get(name, False))
                btn.setMinimumWidth(80)
                btn.setMinimumHeight(28)
                if comment:
                    btn.setToolTip(f"{comment}\n({hex_str})")
                else:
                    btn.setToolTip(hex_str)
                btn.toggled.connect(lambda checked, n=name: self._on_toggle(n, checked))
                self.buttons[name] = btn
                group_btn_list.append((name, btn))
                flow.addWidget(btn)
            group_inner.addLayout(flow)
            group_box.setLayout(group_inner)
            container_layout.addWidget(group_box)
            self._group_widgets.append((group_box, group_btn_list))

        container_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        clear_btn = QPushButton("清除所有")
        clear_btn.clicked.connect(self._clear_all)
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)

    def _filter_buttons(self, text):
        keyword = text.strip().lower()
        # 完整 QSS：同時定義 normal 和 :checked，避免點擊時偽類衝突
        HIGHLIGHT = """
            QPushButton {
                background-color: #1d4060;
                color: #a8d8ff;
                border: 1px solid #3a7ab8;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #005f9e;
                color: #ffffff;
                border: 2px solid #00aaff;
                font-weight: bold;
            }
        """
        DIM = """
            QPushButton {
                background-color: #1e1e24;
                color: #383848;
                border: 1px solid #252535;
            }
            QPushButton:checked {
                background-color: #1a2a3a;
                color: #2a4a5a;
                border: 1px solid #1a3a50;
            }
        """
        for group_box, btn_list in self._group_widgets:
            for name, btn in btn_list:
                if not keyword:
                    btn.setStyleSheet("")
                else:
                    comment = self.viewer.constant_comment_map.get(name, "").lower()
                    matched = keyword in name.lower() or keyword in comment
                    btn.setStyleSheet(HIGHLIGHT if matched else DIM)

    def _on_toggle(self, name, checked):
        self.viewer.constant_buttons_state[name] = checked
        self._apply_timer.start()  # 重新計時，debounce 50ms

    def _clear_all(self):
        for btn in self.buttons.values():
            btn.setChecked(False)
        self.viewer.constant_buttons_state.clear()
        self._apply_timer.start()

# ========================= 滾動速度限制器 =========================
class SlowScrollFilter(QObject):
    def __init__(self, view, speed_ratio=0.06):
        super().__init__(view)
        self.view = view
        self.speed_ratio = speed_ratio

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            scrollbar = self.view.verticalScrollBar()
            if scrollbar and scrollbar.isVisible():
                delta = event.angleDelta().y()
                current = scrollbar.value()
                
                # 強制開啟像素滾動以獲得極細緻的緩速效果
                if self.view.verticalScrollMode() != QAbstractItemView.ScrollPerPixel:
                    self.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
                
                # 像素滾動：大幅縮減每次滾動的像素數 (預設約 6%)
                step = int(delta * self.speed_ratio)
                scrollbar.setValue(current - step)
                event.accept()
                return True
        return super().eventFilter(obj, event)

# ========================= YGOPRODeck 訊號傳遞器 =========================
class YGOPRODeckDownloader(QObject):
    fetched = Signal(int, dict)
    failed = Signal(int)

# ========================= 主程式 =========================
class Viewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("查卡")
        self.resize(1280, 760)
        self.setMinimumSize(1045, 610)

        # 生成扁平下拉箭頭圖示
        arrow_path = os.path.join(os.path.dirname(__file__), "down_arrow.png")
        if not os.path.exists(arrow_path):
            try:
                pixmap = QPixmap(16, 16)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                pen = QPen(QColor("#e0e0e6"), 2)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)
                painter.drawLine(4, 6, 8, 10)
                painter.drawLine(8, 10, 12, 6)
                painter.end()
                pixmap.save(arrow_path)
            except Exception as e:
                print(f"生成下拉箭頭圖示失敗: {e}")

        arrow_url = arrow_path.replace("\\", "/")
        self.setStyleSheet(DARK_STYLE.replace("down_arrow.png", arrow_url))

        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._on_resize_finished)

        self.cards = []
        self.filtered = []
        self.thumbnail_cache = {}
        self.thumbnail_queue = []
        self.thumbnail_timer = QTimer()
        self.thumbnail_timer.timeout.connect(self.load_thumbnails_batch)
        self.thumbnail_timer.setInterval(10)

        self.alias_index = {}
        self.id_map = {}
        self.lua_feature_cache = {}
        self.lua_file_cache = {}
        self.lua_cache_mgr = LuaCacheManager()
        self.ygoprodeck_cache = {}
        self.downloader = YGOPRODeckDownloader()
        self.downloader.fetched.connect(self.on_ygoprodeck_fetched)
        self.downloader.failed.connect(self.on_ygoprodeck_failed)


        self.attribute_buttons = {}
        self.race_buttons = {}
        self.type_buttons = {}
        self.setname_buttons = {}
        self.lv_buttons = {}
        self.scale_buttons = {}
        self.link_buttons = {}
        self.category_buttons = {}

        self.fav_mgr = FavoritesManager()
        self.lflist = LFLIST()
        self.current_lf_label = None
        self.current_limit_filter = 3

        self._current_cid = None
        self._filter_pending = False
        self._filter_running = False
        self._filter_cancel_token = object()  # 取消 token，每次新篩選都換一個

        self.detail_model = DetailCardModel()
        self.detail_delegate = DetailCardDelegate()

        # Lua 常數相關
        self.constants_groups = []
        self.constant_buttons_state = {}
        self.constant_value_map = {}
        self.constant_comment_map = {}
        self.constant_dialog = None
        self._load_constants()

        load_strings_conf()
        self._init_ui()
        self.combo_display_mode.setCurrentIndex(0)
        self.auto_load_default_db()
        self.set_dark_title_bar()

    def set_dark_title_bar(self):
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                
                # 1. 啟用深色模式 (DWMWA_USE_IMMERSIVE_DARK_MODE = 20 / 19)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
                )
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 19, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
                )
                
                # 2. 強制設定標題列背景顏色為極深灰黑色 #0f0f11 (BGR: 0x00110f0f)
                # DWMWA_CAPTION_COLOR = 35
                color_bg = ctypes.c_int(0x00110f0f)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 35, ctypes.byref(color_bg), ctypes.sizeof(color_bg)
                )
                
                # 3. 強制設定標題列文字顏色為白色 (BGR: 0x00ffffff)
                # DWMWA_TEXT_COLOR = 36
                color_text = ctypes.c_int(0x00ffffff)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 36, ctypes.byref(color_text), ctypes.sizeof(color_text)
                )
            except Exception as e:
                print(f"Set dark title bar failed: {e}")

    def _load_constants(self):
        path = os.path.join(os.path.dirname(__file__), "script", "constant.lua")
        if not os.path.exists(path):
            return
        groups = []
        current_group_title = ""
        current_group_items = []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("--"):
                    if current_group_items:
                        groups.append((current_group_title, current_group_items))
                        current_group_items = []
                    title = line[2:].strip()
                    current_group_title = title
                    continue
                match = re.match(r'^(\w+)\s*=\s*(.+?)(?:\s*--\s*(.*))?$', line)
                if match:
                    name = match.group(1)
                    val_str = match.group(2).strip()
                    comment = (match.group(3) or "").strip()
                    if val_str.lower().startswith("0x"):
                        hex_str = val_str.lower()
                    else:
                        try:
                            int_val = int(val_str)
                            hex_str = f"0x{int_val:x}"
                        except ValueError:
                            continue
                    current_group_items.append((name, hex_str))
                    self.constant_value_map[name] = hex_str
                    self.constant_comment_map[name] = comment
            if current_group_items:
                groups.append((current_group_title, current_group_items))
        if not groups and current_group_items:
            groups.append(("", current_group_items))
        self.constants_groups = groups

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 10, 10, 10)
        main_layout.setSpacing(10)

        left_panel = QVBoxLayout()

        # ---------- 搜尋列 (最上面單獨一條) ----------
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜尋卡片...")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(30)
        search_layout.addWidget(self.search, 1)

        self.chk_multi_keyword = QCheckBox("多關鍵字")
        self.chk_multi_keyword.stateChanged.connect(self.apply_filter)
        search_layout.addWidget(self.chk_multi_keyword)

        # ---------- 統一的篩選網格 ----------
        filter_grid = QGridLayout()
        filter_grid.setContentsMargins(0, 0, 0, 0)
        filter_grid.setVerticalSpacing(4)
        filter_grid.setHorizontalSpacing(6)

        # Set column stretches:
        # Col 0 (left labels): width determined by widgets
        # Col 1 (left comboboxes): stretches to fill available space
        # Col 2 (right labels): width determined by widgets
        # Col 3 (right comboboxes): stretches to fill available space (equal to Col 1)
        filter_grid.setColumnStretch(0, 0)
        filter_grid.setColumnStretch(1, 1)
        filter_grid.setColumnStretch(2, 0)
        filter_grid.setColumnStretch(3, 1)

        # ==================== Row 0 ====================
        filter_grid.addWidget(QLabel("模式:"), 0, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.combo_keyword_mode = QComboBox()
        self.combo_keyword_mode.addItems(["AND", "OR"])
        self.combo_keyword_mode.currentIndexChanged.connect(self.apply_filter)
        self.combo_keyword_mode.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        filter_grid.addWidget(self.combo_keyword_mode, 0, 1)

        filter_grid.addWidget(QLabel("範圍:"), 0, 2, Qt.AlignRight | Qt.AlignVCenter)
        self.combo_search_scope = QComboBox()
        self.combo_search_scope.addItems(["卡名+效果", "僅卡名"])
        self.combo_search_scope.currentIndexChanged.connect(self.apply_filter)
        self.combo_search_scope.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        filter_grid.addWidget(self.combo_search_scope, 0, 3)

        # ==================== Row 1 ====================
        filter_grid.addWidget(QLabel("排序:"), 1, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["ID (升)", "ID (降)", "名稱 (升)", "名稱 (降)", "ATK (升)", "ATK (降)", "DEF (升)", "DEF (降)", "等級 (升)", "等級 (降)"])
        self.combo_sort.currentIndexChanged.connect(self.apply_filter)
        self.combo_sort.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        filter_grid.addWidget(self.combo_sort, 1, 1)

        filter_grid.addWidget(QLabel("環境:"), 1, 2, Qt.AlignRight | Qt.AlignVCenter)
        self.combo_env = QComboBox()
        self.combo_env.addItems(["全部環境", "含有 OCG", "含有 TCG", "僅限 OCG", "僅限 TCG"])
        self.combo_env.currentIndexChanged.connect(self.apply_filter)
        self.combo_env.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        filter_grid.addWidget(self.combo_env, 1, 3)

        # ==================== Row 2 ====================
        filter_grid.addWidget(QLabel("禁卡表:"), 2, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.combo_lflist = QComboBox()
        self.combo_lflist.addItem("無限制")
        for label in self.lflist.get_labels():
            self.combo_lflist.addItem(label)
        self.combo_lflist.currentIndexChanged.connect(self.on_lflist_changed)
        self.combo_lflist.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        filter_grid.addWidget(self.combo_lflist, 2, 1)

        filter_grid.addWidget(QLabel("狀態:"), 2, 2, Qt.AlignRight | Qt.AlignVCenter)
        self.combo_limit_filter = QComboBox()
        self.combo_limit_filter.addItems(["全部", "禁止", "限制", "準限制"])
        self.combo_limit_filter.currentIndexChanged.connect(self.on_limit_filter_changed)
        self.combo_limit_filter.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        filter_grid.addWidget(self.combo_limit_filter, 2, 3)

        # ==================== Row 3 ====================
        filter_grid.addWidget(QLabel("收藏夾:"), 3, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.combo_folder = QComboBox()
        self.combo_folder.addItems(self.fav_mgr.get_folders())
        self.combo_folder.currentIndexChanged.connect(self.on_folder_changed)
        self.combo_folder.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        filter_grid.addWidget(self.combo_folder, 3, 1)

        self.btn_add_folder = QPushButton("+")
        self.btn_add_folder.setFixedSize(30, 26)
        self.btn_add_folder.setObjectName("folder_btn")
        self.btn_add_folder.clicked.connect(self.add_folder)
        
        self.btn_del_folder = QPushButton("✕")
        self.btn_del_folder.setFixedSize(30, 26)
        self.btn_del_folder.setObjectName("folder_btn")
        self.btn_del_folder.clicked.connect(self.del_folder)

        self.chk_fav_only = QCheckBox("僅顯示收藏")
        self.chk_fav_only.stateChanged.connect(self.apply_filter)
        self.chk_fav_only.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

        fav_right_layout = QHBoxLayout()
        fav_right_layout.setContentsMargins(0, 0, 0, 0)
        fav_right_layout.setSpacing(4)
        fav_right_layout.addWidget(self.btn_add_folder)
        fav_right_layout.addWidget(self.btn_del_folder)
        fav_right_layout.addWidget(self.chk_fav_only, 1)
        filter_grid.addLayout(fav_right_layout, 3, 3)

        # ==================== Row 4 ====================
        filter_grid.addWidget(QLabel("顯示:"), 4, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.combo_display_mode = QComboBox()
        self.combo_display_mode.addItems(["縮圖模式", "詳細模式"])
        self.combo_display_mode.currentIndexChanged.connect(self.on_display_mode_changed)
        self.combo_display_mode.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        filter_grid.addWidget(self.combo_display_mode, 4, 1)

        self.lbl_columns = QLabel("每行:")
        filter_grid.addWidget(self.lbl_columns, 4, 2, Qt.AlignRight | Qt.AlignVCenter)
        self.combo_columns = QComboBox()
        self.combo_columns.addItems(["1", "2", "3", "4", "5", "6", "8", "10"])
        self.combo_columns.setCurrentText("4")
        self.combo_columns.currentIndexChanged.connect(self.on_columns_changed)
        self.combo_columns.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        filter_grid.addWidget(self.combo_columns, 4, 3)

        left_panel.addLayout(search_layout)
        left_panel.addLayout(filter_grid)

        self.lbl_count = QLabel("全庫 : 0 筆")

        self.stack = QStackedWidget()
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setSpacing(8)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setWordWrap(False)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setUniformItemSizes(True)
        self.list.setFont(QFont("Consolas", 10) if sys.platform == "win32" else QFont("Monospace", 10))
        self.list.setDragEnabled(False)
        self.list.setAcceptDrops(False)
        self.list.setDragDropMode(QListWidget.NoDragDrop)
        self.list.setMovement(QListWidget.Static)

        self.detail_view = QListView()
        self.detail_view.setModel(self.detail_model)
        self.detail_view.setItemDelegate(self.detail_delegate)
        self.detail_view.setSelectionMode(QListView.SingleSelection)
        self.detail_view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.detail_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_view.setSpacing(0)

        # 限制左側縮圖與詳細清單滾動速度，使滑動極其緩慢精準
        self.list_scroll_filter = SlowScrollFilter(self.list, speed_ratio=0.06)
        self.list.installEventFilter(self.list_scroll_filter)

        self.detail_scroll_filter = SlowScrollFilter(self.detail_view, speed_ratio=0.06)
        self.detail_view.installEventFilter(self.detail_scroll_filter)

        self.stack.addWidget(self.list)
        self.stack.addWidget(self.detail_view)

        self.btn_clear_all = QPushButton("清除所有篩選")
        self.btn_clear_all.setObjectName("clear_all_btn")
        self.btn_clear_all.clicked.connect(self.clear_all_filters)

        left_panel.addWidget(self.btn_clear_all)
        left_panel.addWidget(self.lbl_count)
        left_panel.addWidget(self.stack)

        # 中間篩選面板
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        center_widget = self._create_center_panel()
        scroll.setWidget(center_widget)

        # 右側資訊面板
        right_panel = QVBoxLayout()
        self.info = QTextBrowser()
        self.info.setReadOnly(True)
        self.info.setFont(QFont("Microsoft JhengHei", 11))
        self.info.setOpenLinks(False)
        self.info.setFocusPolicy(Qt.NoFocus)
        self.info.anchorClicked.connect(self.handle_info_link)

        self.lbl_image = QLabel("無圖片")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setFixedSize(200, 290)
        self.lbl_image.setStyleSheet("border: 1px solid #3a3a42; background-color: #000;")
        self.lbl_image.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lbl_image.setFocusPolicy(Qt.NoFocus)

        self.btn_fav = QPushButton("收藏")
        self.btn_fav.setObjectName("fav_btn")
        self.btn_fav.setCheckable(True)
        self.btn_fav.clicked.connect(self.toggle_favorite)

        self.btn_wiki = QPushButton("Yugipedia")
        self.btn_wiki.setObjectName("wiki_btn")
        self.btn_wiki.clicked.connect(self.open_wiki)

        self.btn_qa = QPushButton("Q&A")
        self.btn_qa.setObjectName("qa_btn")
        self.btn_qa.setEnabled(False)
        self.btn_qa.clicked.connect(self.open_qa)

        self.btn_detail = QPushButton("詳細數據")
        self.btn_detail.setObjectName("detail_btn")
        self.btn_detail.setEnabled(False)
        self.btn_detail.clicked.connect(self.show_ygoprodeck_detail)

        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(10)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_fav, alignment=Qt.AlignCenter)
        btn_layout.addWidget(self.btn_wiki, alignment=Qt.AlignCenter)
        btn_layout.addWidget(self.btn_qa, alignment=Qt.AlignCenter)
        btn_layout.addWidget(self.btn_detail, alignment=Qt.AlignCenter)
        btn_layout.addStretch()

        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(15)
        bottom_layout.addWidget(self.lbl_image, alignment=Qt.AlignLeft)
        bottom_layout.addLayout(btn_layout)

        right_panel.setSpacing(15)
        right_panel.addWidget(self.info)
        right_panel.addLayout(bottom_layout)

        main_layout.addLayout(left_panel, 4)
        main_layout.addWidget(scroll, 4)
        main_layout.addLayout(right_panel, 4)

        self.search.textChanged.connect(self.apply_filter)
        self.entry_atk.textChanged.connect(self.apply_filter)
        self.entry_def.textChanged.connect(self.apply_filter)
        self.list.currentRowChanged.connect(self.show_card)
        self.detail_view.selectionModel().currentChanged.connect(self.on_detail_selection_changed)
        self.update_list_grid()

    def _reset_group(self, button_dict):
        for btn in button_dict.values():
            if isinstance(btn, TriStateButton):
                btn.reset_state()
            else:
                btn.setChecked(False)
        self.apply_filter()

    def clear_all_filters(self):
        self.search.blockSignals(True)
        self.entry_atk.blockSignals(True)
        self.entry_def.blockSignals(True)
        self.setname_search.blockSignals(True)

        self.search.clear()
        self.entry_atk.clear()
        self.entry_def.clear()
        self.setname_search.clear()

        self.combo_env.setCurrentIndex(0)
        self.chk_fav_only.setChecked(False)
        self.chk_has_alias.setChecked(False)
        self.chk_lua_change_code.setChecked(False)
        self.chk_lua_contact_fusion.setChecked(False)
        self.chk_lua_win.setChecked(False)
        self.combo_keyword_mode.setCurrentIndex(0)
        self.combo_special_mode.setCurrentIndex(0)
        self.combo_search_scope.setCurrentIndex(0)
        self.constant_buttons_state.clear()
        if self.constant_dialog:
            self.constant_dialog.close()
            self.constant_dialog = None

        self.search.blockSignals(False)
        self.entry_atk.blockSignals(False)
        self.entry_def.blockSignals(False)
        self.setname_search.blockSignals(False)

        for btn in self.attribute_buttons.values():
            btn.setChecked(False)
        for btn in self.race_buttons.values():
            btn.setChecked(False)
        for btn in self.type_buttons.values():
            btn.reset_state()
        for btn in self.setname_buttons.values():
            btn.setChecked(False)
            btn.setVisible(True)
        for btn in self.category_buttons.values():
            btn.setChecked(False)
        for btn in self.lv_buttons.values():
            btn.setChecked(False)
        for btn in self.scale_buttons.values():
            btn.setChecked(False)
        for btn in self.link_buttons.values():
            btn.setChecked(False)

        self.apply_filter()

    def filter_setname_buttons(self, text):
        keyword = text.strip().lower()
        for code, btn in self.setname_buttons.items():
            btn_text = btn.text().lower()
            btn.setVisible(not keyword or keyword in btn_text)

    def _create_center_panel(self):
        center_widget = QWidget()
        panel = QVBoxLayout(center_widget)
        panel.setSpacing(5)

        def make_flow_button(text, button_dict, key):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setMinimumWidth(80)
            btn.setFixedHeight(28)
            btn.clicked.connect(self.apply_filter)
            button_dict[key] = btn
            return btn

        # 屬性
        attr_box = QGroupBox("屬性")
        attr_lay = QVBoxLayout()
        attr_top = QHBoxLayout()
        attr_top.addWidget(QLabel("屬性"))
        btn_x_attr = QPushButton("X")
        btn_x_attr.setObjectName("reset_btn")
        btn_x_attr.clicked.connect(lambda: self._reset_group(self.attribute_buttons))
        attr_top.addWidget(btn_x_attr)
        attr_top.addStretch()
        attr_lay.addLayout(attr_top)
        attr_flow = FlowLayout(margin=2, spacing=4)
        attr_flow.setStretchItems(True, threshold=5, uniform_last_line=True)
        for k, v in ATTRIBUTE_MAP.items():
            btn = make_flow_button(v, self.attribute_buttons, k)
            attr_flow.addWidget(btn)
        attr_lay.addLayout(attr_flow)
        attr_box.setLayout(attr_lay)
        panel.addWidget(attr_box)

        # 種族
        race_box = QGroupBox("種族")
        race_lay = QVBoxLayout()
        race_top = QHBoxLayout()
        race_top.addWidget(QLabel("種族"))
        btn_x_race = QPushButton("X")
        btn_x_race.setObjectName("reset_btn")
        btn_x_race.clicked.connect(lambda: self._reset_group(self.race_buttons))
        race_top.addWidget(btn_x_race)
        race_top.addStretch()
        race_lay.addLayout(race_top)
        race_flow = FlowLayout(margin=2, spacing=4)
        race_flow.setStretchItems(True, threshold=5, uniform_last_line=True)
        for k, v in RACE_MAP.items():
            btn = make_flow_button(v, self.race_buttons, k)
            race_flow.addWidget(btn)
        race_lay.addLayout(race_flow)
        race_box.setLayout(race_lay)
        panel.addWidget(race_box)

        # 類型
        type_inc_box = QGroupBox("類型 (左鍵包含 / 右鍵排除)")
        type_inc_lay = QVBoxLayout()
        type_inc_top = QHBoxLayout()
        type_inc_top.addWidget(QLabel("類型"))
        self.combo_type_mode = QComboBox()
        self.combo_type_mode.addItems(["AND", "OR"])
        self.combo_type_mode.currentIndexChanged.connect(self.apply_filter)
        type_inc_top.addWidget(self.combo_type_mode)
        btn_x_type = QPushButton("X")
        btn_x_type.setObjectName("reset_btn")
        btn_x_type.clicked.connect(lambda: self._reset_group(self.type_buttons))
        type_inc_top.addWidget(btn_x_type)
        type_inc_top.addStretch()
        type_inc_lay.addLayout(type_inc_top)

        type_flow = FlowLayout(margin=2, spacing=4)
        type_flow.setStretchItems(True, threshold=5, uniform_last_line=True)
        for k, v in TYPE_CHINESE.items():
            btn = TriStateButton(v)
            btn.setMinimumWidth(80)
            btn.setFixedHeight(28)
            self.type_buttons[k] = btn
            type_flow.addWidget(btn)
        type_inc_lay.addLayout(type_flow)
        type_inc_box.setLayout(type_inc_lay)
        panel.addWidget(type_inc_box)

        # 系列
        setname_box = QGroupBox("系列")
        setname_lay = QVBoxLayout()
        setname_top = QHBoxLayout()
        setname_top.addWidget(QLabel("系列"))
        self.combo_setname_mode = QComboBox()
        self.combo_setname_mode.addItems(["OR", "AND"])
        self.combo_setname_mode.currentIndexChanged.connect(self.apply_filter)
        setname_top.addWidget(self.combo_setname_mode)
        btn_x_setname = QPushButton("X")
        btn_x_setname.setObjectName("reset_btn")
        btn_x_setname.clicked.connect(lambda: self._reset_group(self.setname_buttons))
        setname_top.addWidget(btn_x_setname)
        setname_top.addStretch()
        setname_lay.addLayout(setname_top)

        self.setname_search = QLineEdit()
        self.setname_search.setPlaceholderText("🔍")
        self.setname_search.textChanged.connect(self.filter_setname_buttons)
        setname_lay.addWidget(self.setname_search)

        setname_scroll = QScrollArea()
        setname_scroll.setWidgetResizable(True)
        setname_scroll.setMinimumHeight(180)
        setname_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        setname_scroll_widget = QWidget()
        setname_vbox = QVBoxLayout(setname_scroll_widget)
        setname_vbox.setSpacing(4)
        setname_vbox.setContentsMargins(0, 0, 5, 0)
        sorted_setnames = sorted(SETNAME_MAP.items(), key=lambda x: x[0])
        for code, name in sorted_setnames:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.clicked.connect(self.apply_filter)
            self.setname_buttons[code] = btn
            setname_vbox.addWidget(btn)
        setname_scroll.setWidget(setname_scroll_widget)
        setname_lay.addWidget(setname_scroll)
        setname_box.setLayout(setname_lay)
        panel.addWidget(setname_box)

        # 效果分類
        category_box = QGroupBox("效果分類")
        category_lay = QVBoxLayout()
        category_top = QHBoxLayout()
        category_top.addWidget(QLabel("效果分類"))
        self.combo_category_mode = QComboBox()
        self.combo_category_mode.addItems(["OR", "AND"])
        self.combo_category_mode.currentIndexChanged.connect(self.apply_filter)
        category_top.addWidget(self.combo_category_mode)
        btn_x_category = QPushButton("X")
        btn_x_category.setObjectName("reset_btn")
        btn_x_category.clicked.connect(lambda: self._reset_group(self.category_buttons))
        category_top.addWidget(btn_x_category)
        category_top.addStretch()
        category_lay.addLayout(category_top)
        category_flow = FlowLayout(margin=2, spacing=4)
        category_flow.setStretchItems(True, threshold=5, uniform_last_line=True)
        sorted_categories = sorted(CATEGORY_MAP.items(), key=lambda x: x[0])
        for code, name in sorted_categories:
            btn = make_flow_button(name, self.category_buttons, code)
            category_flow.addWidget(btn)
        category_lay.addLayout(category_flow)
        category_box.setLayout(category_lay)
        panel.addWidget(category_box)

        # 星數/階級/L值
        lv_box = QGroupBox("星數/階級/L值")
        lv_lay = QVBoxLayout()
        lv_top = QHBoxLayout()
        lv_top.addWidget(QLabel("星數/階級/L值"))
        btn_x_lv = QPushButton("X")
        btn_x_lv.setObjectName("reset_btn")
        btn_x_lv.clicked.connect(lambda: self._reset_group(self.lv_buttons))
        lv_top.addWidget(btn_x_lv)
        lv_top.addStretch()
        lv_lay.addLayout(lv_top)
        lv_flow = FlowLayout(margin=2, spacing=3)
        lv_flow.setStretchItems(True, threshold=5, uniform_last_line=True)
        for i in range(1, 14):
            btn = make_flow_button(str(i), self.lv_buttons, i)
            lv_flow.addWidget(btn)
        lv_lay.addLayout(lv_flow)
        lv_box.setLayout(lv_lay)
        panel.addWidget(lv_box)

        # 刻度
        scale_box = QGroupBox("刻度")
        scale_lay = QVBoxLayout()
        scale_top = QHBoxLayout()
        scale_top.addWidget(QLabel("刻度"))
        btn_x_scale = QPushButton("X")
        btn_x_scale.setObjectName("reset_btn")
        btn_x_scale.clicked.connect(lambda: self._reset_group(self.scale_buttons))
        scale_top.addWidget(btn_x_scale)
        scale_top.addStretch()
        scale_lay.addLayout(scale_top)
        scale_flow = FlowLayout(margin=2, spacing=3)
        scale_flow.setStretchItems(True, threshold=5, uniform_last_line=True)
        for i in range(14):
            btn = make_flow_button(str(i), self.scale_buttons, i)
            scale_flow.addWidget(btn)
        scale_lay.addLayout(scale_flow)
        scale_box.setLayout(scale_lay)
        panel.addWidget(scale_box)

        # 連結箭頭
        link_box = QGroupBox("連結箭頭")
        link_lay = QVBoxLayout()
        link_top = QHBoxLayout()
        link_top.addWidget(QLabel("連結箭頭"))
        self.combo_link_mode = QComboBox()
        self.combo_link_mode.addItems(["OR", "AND"])
        self.combo_link_mode.currentIndexChanged.connect(self.apply_filter)
        link_top.addWidget(self.combo_link_mode)
        btn_x_link = QPushButton("X")
        btn_x_link.setObjectName("reset_btn")
        btn_x_link.clicked.connect(lambda: self._reset_group(self.link_buttons))
        link_top.addWidget(btn_x_link)
        link_top.addStretch()
        link_lay.addLayout(link_top)

        link_grid = QGridLayout()
        link_grid.setSpacing(2)
        for r in range(3):
            for c in range(3):
                if r == 1 and c == 1:
                    lbl = QLabel("")
                    lbl.setFixedSize(36, 36)
                    link_grid.addWidget(lbl, r, c, alignment=Qt.AlignCenter)
                else:
                    btn = QPushButton("")
                    btn.setObjectName("link_btn")
                    btn.setCheckable(True)
                    btn.setFixedSize(36, 36)
                    btn.clicked.connect(self.apply_filter)
                    arrow_symbols = {(0,0):"↙", (1,0):"↓", (2,0):"↘", (0,1):"←", (2,1):"→", (0,2):"↖", (1,2):"↑", (2,2):"↗"}
                    btn.setText(arrow_symbols[(r,c)])
                    mask = LINK_MARKERS[(r,c)]
                    self.link_buttons[mask] = btn
                    link_grid.addWidget(btn, 2 - c, r)
        
        link_container = QHBoxLayout()
        link_container.addStretch()
        link_container.addLayout(link_grid)
        link_container.addStretch()
        link_lay.addLayout(link_container)
        link_box.setLayout(link_lay)
        panel.addWidget(link_box)

        # ATK/DEF
        stat_box = QGroupBox("ATK / DEF")
        stat_grid = QGridLayout()
        stat_grid.setContentsMargins(10, 10, 10, 10)
        stat_grid.setSpacing(8)
        stat_grid.addWidget(QLabel("ATK:"), 0, 0)
        self.entry_atk = QLineEdit()
        self.entry_atk.setPlaceholderText("例: >=2500 或 =? 或 atk=def")
        stat_grid.addWidget(self.entry_atk, 0, 1)
        stat_grid.addWidget(QLabel("DEF:"), 1, 0)
        self.entry_def = QLineEdit()
        self.entry_def.setPlaceholderText("")
        stat_grid.addWidget(self.entry_def, 1, 1)
        stat_box.setLayout(stat_grid)
        panel.addWidget(stat_box)

        # 特殊篩選
        special_box = QGroupBox("特殊篩選")
        special_layout = QVBoxLayout()
        special_layout.setContentsMargins(10, 10, 10, 10)

        special_mode_layout = QHBoxLayout()
        special_mode_layout.addWidget(QLabel("特殊條件模式:"))
        self.combo_special_mode = QComboBox()
        self.combo_special_mode.addItems(["OR", "AND"])
        self.combo_special_mode.currentIndexChanged.connect(self.apply_filter)
        special_mode_layout.addWidget(self.combo_special_mode)
        special_mode_layout.addStretch()
        special_layout.addLayout(special_mode_layout)

        self.chk_has_alias = QCheckBox("有同名卡 (alias != 0)")
        self.chk_has_alias.stateChanged.connect(self.apply_filter)
        special_layout.addWidget(self.chk_has_alias)

        self.chk_lua_change_code = QCheckBox("🔁 可改變卡片名稱")
        self.chk_lua_change_code.stateChanged.connect(self.apply_filter)
        self.chk_lua_contact_fusion = QCheckBox("🌀 接觸融合素材")
        self.chk_lua_contact_fusion.stateChanged.connect(self.apply_filter)
        self.chk_lua_win = QCheckBox("🏆 特殊勝利條件")
        self.chk_lua_win.stateChanged.connect(self.apply_filter)
        special_layout.addWidget(self.chk_lua_change_code)
        special_layout.addWidget(self.chk_lua_contact_fusion)
        special_layout.addWidget(self.chk_lua_win)

        self.btn_lua_constants = QPushButton("Lua 腳本常數")
        self.btn_lua_constants.clicked.connect(self.open_constant_dialog)
        special_layout.addWidget(self.btn_lua_constants)

        special_box.setLayout(special_layout)
        panel.addWidget(special_box)

        return center_widget

    def open_constant_dialog(self):
        if self.constant_dialog is None:
            self.constant_dialog = ConstantDialog(self)
        self.constant_dialog.show()
        self.constant_dialog.raise_()

    def auto_load_default_db(self):
        default_path = os.path.join(os.path.dirname(__file__), "cards.cdb")
        if os.path.exists(default_path):
            self.load_database_by_path(default_path)

    def load_database_by_path(self, path):
        try:
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            query = """
                SELECT datas.id, texts.name, texts.desc,
                       datas.type, datas.atk, datas.def,
                       datas.level, datas.race, datas.attribute, datas.setcode,
                       datas.alias, datas.ot, datas.category
                FROM datas JOIN texts ON datas.id=texts.id
            """
            self.cards = list(cur.execute(query))
            conn.close()
            self._build_alias_index()
            self.thumbnail_cache.clear()
            self.thumbnail_queue.clear()
            self.thumbnail_timer.stop()
            self.lua_feature_cache.clear()
            self.lua_file_cache.clear()
            self.apply_filter()
            # 啟動 Lua 檢索快取建置/載入
            cids = [c[0] for c in self.cards]
            self.lbl_count.setText("正在建立/載入 Lua 檢索快取...")
            self.lua_cache_mgr.load_or_build(
                cids,
                progress_callback=self._on_lua_cache_progress,
                finished_callback=self._on_lua_cache_finished
            )
        except Exception as e:
            print(f"載入 CDB 失敗: {e}")

    def _on_lua_cache_progress(self, pct):
        self.lbl_count.setText(f"正在建立/載入 Lua 檢索快取... {pct}%")

    def _on_lua_cache_finished(self):
        self.apply_filter()
        txt = self.lbl_count.text()
        if not txt.endswith("Lua 索引完成"):
            self.lbl_count.setText(txt + "  ✅ Lua 索引完成")




    def _build_alias_index(self):
        self.alias_index.clear()
        self.id_map.clear()
        for card in self.cards:
            cid = card[0]
            self.id_map[cid] = card
            alias = card[10]
            if alias != 0:
                self.alias_index.setdefault(alias, []).append(card)

    def _match_stat_condition(self, card_value, cond_str, opposite_value=None):
        cond = cond_str.strip().lower()
        if not cond:
            return True
        if cond == "=?" or cond == "?":
            return card_value == -2
        if cond in ["atk=def", "def=atk"] and opposite_value is not None:
            return card_value == opposite_value
        match = re.match(r"^([>=<!]+)?\s*(-?\d+)$", cond)
        if match:
            op, val_str = match.groups()
            target_val = int(val_str)
            if not op or op == "=":
                return card_value == target_val
            if op == ">":
                return card_value > target_val
            if op == "<":
                return card_value < target_val
            if op == ">=":
                return card_value >= target_val
            if op == "<=":
                return card_value <= target_val
            if op == "!=":
                return card_value != target_val
        return False

    def load_thumbnails_batch(self):
        batch_size = 8
        processed = 0
        cache_key_suffix = self.current_lf_label or "none"
        while self.thumbnail_queue and processed < batch_size:
            item, cid = self.thumbnail_queue.pop(0)
            if item is None or item.listWidget() is None:
                continue
            cache_key = (cid, cache_key_suffix)
            icon = self.thumbnail_cache.get(cache_key)
            if icon is None:
                img_path = os.path.join(os.path.dirname(__file__), "pics", f"{cid}.jpg")
                icon_size = self.list.iconSize()
                if icon_size.width() <= 0:
                    icon_size = QSize(120, 160)
                if os.path.exists(img_path):
                    pixmap = QPixmap(img_path)
                    pixmap = pixmap.scaled(icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    if self.current_lf_label:
                        limit = self.lflist.get_limit(cid, self.current_lf_label)
                        if limit != 3:
                            painter = QPainter(pixmap)
                            painter.setRenderHint(QPainter.Antialiasing)
                            colors = {0: QColor(220, 50, 50), 1: QColor(255, 180, 0), 2: QColor(50, 200, 50)}
                            color = colors.get(limit, QColor(128, 128, 128))
                            radius = min(pixmap.width(), pixmap.height()) // 7
                            if radius < 10:
                                radius = 10
                            x = 4
                            y = 4
                            painter.setPen(QPen(QColor(40, 40, 50), 1))
                            painter.setBrush(QBrush(color))
                            painter.drawEllipse(x, y, radius * 2, radius * 2)
                            painter.setPen(QPen(Qt.white, 1))
                            painter.setFont(QFont("Arial", radius, QFont.Bold))
                            texts = {0: "禁", 1: "限", 2: "準"}
                            painter.drawText(x, y, radius * 2, radius * 2, Qt.AlignCenter, texts.get(limit, ""))
                            painter.end()
                    icon = QIcon(pixmap)
                else:
                    default_pix = QPixmap(icon_size)
                    default_pix.fill(QColor(80, 80, 80))
                    icon = QIcon(default_pix)
                self.thumbnail_cache[cache_key] = icon
            item.setIcon(icon)
            processed += 1

        if self.thumbnail_queue:
            self.thumbnail_timer.start()
        else:
            self.thumbnail_timer.stop()

    def on_lflist_changed(self, idx):
        if idx == 0:
            self.current_lf_label = None
        else:
            labels = self.lflist.get_labels()
            if idx - 1 < len(labels):
                self.current_lf_label = labels[idx - 1]
        self.thumbnail_cache.clear()
        self.apply_filter()

    def on_limit_filter_changed(self, idx):
        mapping = {0: 3, 1: 0, 2: 1, 3: 2}
        self.current_limit_filter = mapping.get(idx, 3)
        self.apply_filter()

    def on_folder_changed(self, idx):
        if idx >= 0:
            folder = self.combo_folder.currentText()
            self.fav_mgr.set_current(folder)
            self.apply_filter()
            if self._current_cid is not None:
                is_fav = self.fav_mgr.contains(folder, self._current_cid)
                self.btn_fav.setChecked(is_fav)
                self.btn_fav.setText("取消收藏" if is_fav else "收藏")

    def add_folder(self):
        name, ok = QInputDialog.getText(self, "新增收藏夾", "請輸入新收藏夾名稱:")
        if ok and name.strip():
            if self.fav_mgr.add_folder(name.strip()):
                self.combo_folder.addItem(name.strip())
                self.combo_folder.setCurrentText(name.strip())
            else:
                QMessageBox.warning(self, "錯誤", "收藏夾名稱已存在或無效")

    def del_folder(self):
        current = self.combo_folder.currentText()
        if current == "預設":
            QMessageBox.information(self, "提示", "預設收藏夾不可刪除")
            return
        reply = QMessageBox.question(self, "確認刪除", f"確定要刪除收藏夾「{current}」嗎？\n其內收藏將遺失。",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.fav_mgr.remove_folder(current):
                self.combo_folder.removeItem(self.combo_folder.currentIndex())
                self.combo_folder.setCurrentText("預設")
                self.apply_filter()

    def toggle_favorite(self):
        if self._current_cid is None:
            return
        cid = self._current_cid
        folder = self.combo_folder.currentText()
        if self.btn_fav.isChecked():
            self.fav_mgr.add_card(folder, cid)
            self.btn_fav.setText("取消收藏")
        else:
            self.fav_mgr.remove_card(folder, cid)
            self.btn_fav.setText("收藏")
        if self.chk_fav_only.isChecked():
            self.apply_filter()

    def handle_info_link(self, url):
        link = url.toString()
        if not self._current_cid:
            return
        card = self.id_map.get(self._current_cid)
        if not card:
            return
        cid, name, desc, ctype, atk, df, level, race, attr, setcode, alias, ot, category = card

        clipboard = QApplication.clipboard()
        if link == "copy:name":
            clipboard.setText(name)
            QToolTip.showText(QCursor.pos(), "已複製卡名")
        elif link == "copy:code":
            clipboard.setText(str(cid).zfill(8))
            QToolTip.showText(QCursor.pos(), "已複製卡片密碼")
        elif link == "copy:desc":
            clipboard.setText(desc)
            QToolTip.showText(QCursor.pos(), "已複製卡片效果")

    def open_wiki(self):
        if self._current_cid is None:
            return
        import webbrowser
        url = f"https://yugipedia.com/wiki/{str(self._current_cid).zfill(8)}"
        webbrowser.open(url)

    def open_qa(self):
        if self._current_cid is None:
            return
        ygopro_data = self.ygoprodeck_cache.get(self._current_cid)
        if isinstance(ygopro_data, dict):
            misc = ygopro_data.get("misc_info", [{}])[0]
            konami_id = misc.get("konami_id")
            if konami_id:
                import webbrowser
                url = f"https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid={konami_id}"
                webbrowser.open(url)

    def show_ygoprodeck_detail(self):
        if self._current_cid is None:
            return
        ygopro_data = self.ygoprodeck_cache.get(self._current_cid)
        if isinstance(ygopro_data, dict):
            dialog = CardDetailDialog(self, ygopro_data)
            dialog.exec()

    def fetch_ygoprodeck_info(self, cid):
        def worker():
            import urllib.request
            import json
            import ssl
            import traceback

            # 建立未驗證的 SSL 上下文，避開 Windows 平台常見的 Python SSL 證書驗證錯誤
            context = ssl._create_unverified_context()
            
            # 第一輪：優先使用原始 ID 查詢
            url1 = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?id={str(cid)}&misc=yes&format=genesys%20ocg"
            req1 = urllib.request.Request(
                url1,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            
            try:
                with urllib.request.urlopen(req1, timeout=5, context=context) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if "data" in data and len(data["data"]) > 0:
                        card_info = data["data"][0]
                        self.downloader.fetched.emit(cid, card_info)
                        return
            except Exception as e:
                # 記錄第一輪失敗日誌
                try:
                    with open("api_error_log.txt", "a", encoding="utf-8") as log_f:
                        log_f.write(f"First attempt failed for {cid} (url: {url1}): {e}\n")
                except:
                    pass

            # 第二輪：後備方案使用補滿 8 位的 ID 查詢
            url2 = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?id={str(cid).zfill(8)}&misc=yes&format=genesys%20ocg"
            req2 = urllib.request.Request(
                url2,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            
            try:
                with urllib.request.urlopen(req2, timeout=5, context=context) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if "data" in data and len(data["data"]) > 0:
                        card_info = data["data"][0]
                        self.downloader.fetched.emit(cid, card_info)
                        return
            except Exception as e:
                # 記錄第二輪失敗日誌
                try:
                    with open("api_error_log.txt", "a", encoding="utf-8") as log_f:
                        log_f.write(f"Second attempt failed for {cid} (url: {url2}): {e}\n" + traceback.format_exc() + "\n")
                except:
                    pass

            # 兩輪皆失敗，回報失敗
            self.downloader.failed.emit(cid)

        import threading
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def on_ygoprodeck_fetched(self, cid, card_info):
        self.ygoprodeck_cache[cid] = card_info
        if self._current_cid == cid:
            display_mode = self.combo_display_mode.currentText()
            if display_mode == "詳細模式":
                current_idx = self.detail_view.selectionModel().currentIndex()
                if current_idx.isValid():
                    self.show_card(current_idx.row())
            else:
                row = self.list.currentRow()
                if row >= 0:
                    self.show_card(row)

    def on_ygoprodeck_failed(self, cid):
        self.ygoprodeck_cache[cid] = "failed"
        if self._current_cid == cid:
            display_mode = self.combo_display_mode.currentText()
            if display_mode == "詳細模式":
                current_idx = self.detail_view.selectionModel().currentIndex()
                if current_idx.isValid():
                    self.show_card(current_idx.row())
            else:
                row = self.list.currentRow()
                if row >= 0:
                    self.show_card(row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_timer.start(150)

    def _on_resize_finished(self):
        self.thumbnail_timer.stop()
        self.thumbnail_queue.clear()
        self.thumbnail_cache.clear()
        self.update_list_grid()
        if self._filter_running:
            self._filter_pending = True
        else:
            self.apply_filter()

    def update_list_grid(self):
        mode = self.combo_display_mode.currentText()
        if mode == "詳細模式":
            self.stack.setCurrentIndex(1)
            self.list.setGridSize(QSize())
            self.list.setSpacing(0)
            return

        self.stack.setCurrentIndex(0)
        self.list.setViewMode(QListWidget.IconMode)
        if self.list.width() <= 0:
            return
        margin = 8
        spacing = 8
        self.list.setSpacing(spacing)
        cols = int(self.combo_columns.currentText())
        avail_width = self.list.width() - margin * 2
        if cols > 1:
            item_width = (avail_width - spacing * (cols - 1)) // cols
        else:
            item_width = avail_width
        if item_width < 60:
            item_width = 60
        item_height = int(item_width * 1.4) + 30
        if item_height < 100:
            item_height = 100
        self.list.setGridSize(QSize(item_width, item_height))
        icon_width = item_width - 4
        icon_height = int(icon_width * 1.3)
        self.list.setIconSize(QSize(icon_width, icon_height))

    def on_display_mode_changed(self, idx):
        is_thumbnail = (self.combo_display_mode.currentText() == "縮圖模式")
        self.lbl_columns.setVisible(is_thumbnail)
        self.combo_columns.setVisible(is_thumbnail)
        self.thumbnail_cache.clear()
        self.update_list_grid()
        self.apply_filter()

    def on_columns_changed(self, idx):
        if self.combo_display_mode.currentText() == "縮圖模式":
            self.thumbnail_cache.clear()
            self.update_list_grid()
            self.apply_filter()

    def on_detail_selection_changed(self, current, previous):
        if current.isValid():
            idx = current.row()
            self.show_card(idx)
        else:
            self.info.clear()
            self.lbl_image.setText("無圖片")
            self.btn_fav.setChecked(False)
            self.btn_fav.setText("收藏")
            self._current_cid = None

    def _get_lua_file_content(self, cid):
        if cid in self.lua_file_cache:
            return self.lua_file_cache[cid]
        script_path = os.path.join(os.path.dirname(__file__), "script", f"c{cid}.lua")
        if os.path.exists(script_path):
            try:
                with open(script_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                self.lua_file_cache[cid] = content
                return content
            except:
                self.lua_file_cache[cid] = ""
                return ""
        self.lua_file_cache[cid] = ""
        return ""

    def apply_filter(self):
        if self._filter_running:
            self._filter_pending = True
            return
        self._filter_running = True
        self._filter_pending = False

        raw_key = self.search.text().strip()
        multi = self.chk_multi_keyword.isChecked()
        mode = self.combo_keyword_mode.currentText()
        search_scope = self.combo_search_scope.currentText()

        atk_cond = self.entry_atk.text().strip()
        def_cond = self.entry_def.text().strip()
        env_mode = self.combo_env.currentText()
        sort_mode = self.combo_sort.currentText()
        fav_only = self.chk_fav_only.isChecked()
        lf_label = self.current_lf_label
        limit_filter = self.current_limit_filter
        folder = self.combo_folder.currentText()

        active_attrs = [k for k, v in self.attribute_buttons.items() if v.isChecked()]
        active_races = [k for k, v in self.race_buttons.items() if v.isChecked()]
        active_types_inc = [k for k, v in self.type_buttons.items() if v.get_state() == 1]
        active_types_exc = [k for k, v in self.type_buttons.items() if v.get_state() == 2]
        active_setnames = [k for k, v in self.setname_buttons.items() if v.isChecked()]
        active_categories = [k for k, v in self.category_buttons.items() if v.isChecked()]
        active_lvs = [k for k, v in self.lv_buttons.items() if v.isChecked()]
        active_scales = [k for k, v in self.scale_buttons.items() if v.isChecked()]
        active_links = [k for k, v in self.link_buttons.items() if v.isChecked()]

        SPECIAL_PERM_MAGIC = 0x1000000000000000
        SPECIAL_PERM_TRAP  = 0x2000000000000000
        SPECIAL_RIT_MONSTER = 0x4000000000000000
        SPECIAL_RIT_MAGIC   = 0x8000000000000000
        inc_perm_magic = SPECIAL_PERM_MAGIC in active_types_inc
        inc_perm_trap  = SPECIAL_PERM_TRAP  in active_types_inc
        inc_rit_monster = SPECIAL_RIT_MONSTER in active_types_inc
        inc_rit_magic   = SPECIAL_RIT_MAGIC   in active_types_inc
        normal_types_inc = [t for t in active_types_inc if t not in (SPECIAL_PERM_MAGIC, SPECIAL_PERM_TRAP, SPECIAL_RIT_MONSTER, SPECIAL_RIT_MAGIC)]
        exc_perm_magic = SPECIAL_PERM_MAGIC in active_types_exc
        exc_perm_trap  = SPECIAL_PERM_TRAP  in active_types_exc
        exc_rit_monster = SPECIAL_RIT_MONSTER in active_types_exc
        exc_rit_magic   = SPECIAL_RIT_MAGIC   in active_types_exc
        normal_types_exc = [t for t in active_types_exc if t not in (SPECIAL_PERM_MAGIC, SPECIAL_PERM_TRAP, SPECIAL_RIT_MONSTER, SPECIAL_RIT_MAGIC)]

        self.filtered = []
        self.thumbnail_timer.stop()    # 必須在 list.clear() 之前停，否則可能跑到已刪除的 item
        self.thumbnail_queue.clear()
        self.list.clear()

        type_inc_mode = self.combo_type_mode.currentText()
        link_mode = self.combo_link_mode.currentText()
        category_mode = self.combo_category_mode.currentText()

        default_pix = QPixmap(self.list.iconSize())
        default_pix.fill(QColor(60, 60, 70))
        default_icon = QIcon(default_pix)

        special_conditions_check = []
        if self.chk_has_alias.isChecked():
            special_conditions_check.append("has_alias")
        if self.chk_lua_change_code.isChecked():
            special_conditions_check.append("🔁 可改變卡片名稱")
        if self.chk_lua_contact_fusion.isChecked():
            special_conditions_check.append("🌀 接觸融合素材")
        if self.chk_lua_win.isChecked():
            special_conditions_check.append("🏆 特殊勝利條件")

        special_mode = self.combo_special_mode.currentText() if special_conditions_check else "OR"

        # 收集勾選的常數名稱 (只用名稱比對，並利用完整單詞匹配)
        active_constant_names = [name for name, checked in self.constant_buttons_state.items() if checked]

        # ── Phase 1：純邏輯篩選（不讀任何 lua 檔，速度快）──────────────────
        candidates = []
        for c in self.cards:
            cid, name, desc, ctype, atk, df, level, race, attr, setcode, alias, ot, category = c

            if raw_key:
                if multi:
                    keywords = [kw.strip() for kw in raw_key.split() if kw.strip()]
                    if keywords:
                        if mode == "AND":
                            if not all(
                                (kw.lower() in name.lower()) or
                                (str(cid) == kw) or
                                (kw.lower() in desc.lower() if search_scope == "卡名+效果" else False)
                                for kw in keywords
                            ):
                                continue
                        else:
                            if not any(
                                (kw.lower() in name.lower()) or
                                (str(cid) == kw) or
                                (kw.lower() in desc.lower() if search_scope == "卡名+效果" else False)
                                for kw in keywords
                            ):
                                continue
                else:
                    key = raw_key.lower()
                    hit = key in name.lower() or (str(cid) == raw_key)
                    if search_scope == "卡名+效果":
                        hit = hit or key in desc.lower()
                    if not hit:
                        continue

            if not self._match_stat_condition(atk, atk_cond, df):
                continue
            if not self._match_stat_condition(df, def_cond, atk):
                continue
            if env_mode == "含有 OCG" and ot == 2:
                continue
            if env_mode == "含有 TCG" and ot == 1:
                continue
            if env_mode == "僅限 OCG" and ot != 1:
                continue
            if env_mode == "僅限 TCG" and ot != 2:
                continue
            if active_attrs and attr not in active_attrs:
                continue
            if active_races and not any(race & r for r in active_races):
                continue

            if normal_types_exc and any(ctype & t for t in normal_types_exc):
                continue
            if exc_perm_magic and (ctype & TYPE_MAGIC and ctype & 0x20000):
                continue
            if exc_perm_trap  and (ctype & TYPE_TRAP  and ctype & 0x20000):
                continue
            if exc_rit_monster and (ctype & TYPE_MONSTER and ctype & 0x80):
                continue
            if exc_rit_magic   and (ctype & TYPE_MAGIC   and ctype & 0x80):
                continue

            link_type_checked = (TYPE_LINK in normal_types_inc)
            other_types_inc = [t for t in normal_types_inc if t != TYPE_LINK]

            if other_types_inc:
                if type_inc_mode == "AND":
                    if not all((ctype & t) == t for t in other_types_inc):
                        continue
                else:
                    if not any(ctype & t for t in other_types_inc):
                        continue

            if link_type_checked and not bool(ctype & TYPE_LINK): continue
            if inc_perm_magic and not (ctype & TYPE_MAGIC and ctype & 0x20000): continue
            if inc_perm_trap and not (ctype & TYPE_TRAP and ctype & 0x20000): continue
            if inc_rit_monster and not (ctype & TYPE_MONSTER and ctype & 0x80): continue
            if inc_rit_magic and not (ctype & TYPE_MAGIC and ctype & 0x80): continue
            if active_links:
                if not (ctype & TYPE_LINK): continue
                if link_mode == "AND":
                    if not all(df & m for m in active_links): continue
                else:
                    if not any(df & m for m in active_links): continue
            card_archetypes = []
            temp_setcode = setcode if setcode is not None else 0
            for _ in range(4):
                sub_code = temp_setcode & 0xFFFF
                if sub_code > 0: card_archetypes.append(sub_code)
                temp_setcode >>= 16
            if active_setnames:
                if self.combo_setname_mode.currentText() == "AND":
                    if not all(s in card_archetypes for s in active_setnames): continue
                else:
                    if not any(s in card_archetypes for s in active_setnames): continue
            if active_categories:
                if category_mode == "AND":
                    if not all((category & c) == c for c in active_categories): continue
                else:
                    if not any(category & c for c in active_categories): continue
            card_lv = level & 0xFFFF
            if active_lvs and card_lv not in active_lvs: continue
            card_scale = (level >> 24) & 0xFF
            if active_scales and card_scale not in active_scales: continue
            if lf_label and limit_filter != 3:
                limit = self.lflist.get_limit(cid, lf_label)
                if limit != limit_filter: continue
            if fav_only and not self.fav_mgr.contains(folder, cid): continue
            candidates.append(c)

        # ── Phase 2：需要 lua 篩選時，使用快取集合極速過濾 ──────────────────
        needs_special = bool(active_constant_names or special_conditions_check)
        display_mode = self.combo_display_mode.currentText()

        if needs_special:
            if not self.lua_cache_mgr.is_loaded:
                # 快取還沒準備好，先跳過 Lua 篩選，直接顯示，並在狀態列提示
                self._apply_filter_finalize(candidates, sort_mode, display_mode, default_icon)
                self.lbl_count.setText(self.lbl_count.text() + " ⏳ (Lua 檢索快取建置中...)")
                self._filter_running = False
                if self._filter_pending:
                    self._filter_pending = False
                    self.apply_filter()
                return

            # 快取已準備好，執行極速的 set 集合運算
            lua_match_set = None

            if special_mode == "AND":
                # 交集模式
                if "has_alias" in special_conditions_check:
                    alias_cids = {c[0] for c in candidates if c[10] != 0}
                    lua_match_set = alias_cids

                for cn in active_constant_names:
                    cids = self.lua_cache_mgr.get_matching_cids(cn)
                    if lua_match_set is None:
                        lua_match_set = cids
                    else:
                        lua_match_set = lua_match_set.intersection(cids)

                for cond in special_conditions_check:
                    if cond != "has_alias":
                        cids = self.lua_cache_mgr.get_matching_cids(cond)
                        if lua_match_set is None:
                            lua_match_set = cids
                        else:
                            lua_match_set = lua_match_set.intersection(cids)

                if lua_match_set is None:
                    lua_match_set = set()
            else:
                # 聯集模式
                lua_match_set = set()
                if "has_alias" in special_conditions_check:
                    alias_cids = {c[0] for c in candidates if c[10] != 0}
                    lua_match_set.update(alias_cids)

                for cn in active_constant_names:
                    lua_match_set.update(self.lua_cache_mgr.get_matching_cids(cn))

                for cond in special_conditions_check:
                    if cond != "has_alias":
                        lua_match_set.update(self.lua_cache_mgr.get_matching_cids(cond))

            # 進行過濾
            candidates = [c for c in candidates if c[0] in lua_match_set]

        # 直接更新 UI
        self._apply_filter_finalize(candidates, sort_mode, display_mode, default_icon)


    def _apply_filter_finalize(self, result, sort_mode, display_mode, default_icon):
        self.filtered = result
        def sort_key(card):
            cid, name, desc, ctype, atk, df, level, race, attr, setcode, alias, ot, category = card
            field = sort_mode.split(" ")[0]
            if field == "ID": return cid
            elif field == "名稱": return name
            elif field == "ATK": return atk if atk != -2 else -99999
            elif field == "DEF": return df if df != -2 else -99999
            elif field == "等級": return level & 0xFFFF
            else: return cid

        reverse_sort = "（降）" in sort_mode or "(降)" in sort_mode
        self.filtered.sort(key=sort_key, reverse=reverse_sort)

        if display_mode == "縮圖模式":
            self.stack.setCurrentIndex(0)
            self.list.setViewMode(QListWidget.IconMode)
            self.list.setSpacing(8)
            self.update_list_grid()
            for c in self.filtered:
                cid, name, desc, ctype, atk, df, level, race, attr, setcode, alias, ot, category = c
                item = QListWidgetItem(name)
                item.setToolTip(name)
                item.setSizeHint(QSize(self.list.gridSize().width(), self.list.gridSize().height()))
                cache_key = (cid, self.current_lf_label or "none")
                icon = self.thumbnail_cache.get(cache_key)
                if icon is not None:
                    item.setIcon(icon)
                else:
                    item.setIcon(default_icon)
                    self.thumbnail_queue.append((item, cid))
                self.list.addItem(item)
        else:
            self.stack.setCurrentIndex(1)
            self.detail_model.set_cards(self.filtered)
            self.detail_model.set_lflist_info(self.lflist, self.current_lf_label)
            self.detail_view.clearSelection()

        self.lbl_count.setText(f"篩選出 : {len(self.filtered)} / 全庫 : {len(self.cards)} 筆")
        self._filter_running = False
        if self._filter_pending:
            self._filter_pending = False
            self.apply_filter()

        if self.thumbnail_queue and display_mode == "縮圖模式":
            self.thumbnail_timer.start()
        else:
            self.thumbnail_timer.stop()

    def _get_lua_features(self, cid, name, alias):
        target_id = cid
        if alias != 0:
            orig_card = self.id_map.get(alias)
            if orig_card:
                orig_name = orig_card[1]
                if orig_name == name:
                    target_id = alias
        if target_id in self.lua_feature_cache:
            return self.lua_feature_cache[target_id]

        features = []
        script_path = os.path.join(os.path.dirname(__file__), "script", f"c{target_id}.lua")
        if os.path.exists(script_path):
            try:
                with open(script_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if "aux.EnableChangeCode" in content:
                    features.append("🔁 可改變卡片名稱")
                if "aux.AddContactFusionProcedure" in content or "Contact_Fusion" in content or "ContactFusion" in content:
                    features.append("🌀 接觸融合素材")
                if "Duel.Win" in content:
                    features.append("🏆 特殊勝利條件")
            except:
                pass
        self.lua_feature_cache[target_id] = features
        return features

    def show_card(self, idx):
        display_mode = self.combo_display_mode.currentText()
        if display_mode == "詳細模式":
            if idx < 0 or idx >= len(self.filtered):
                self.info.clear()
                self.lbl_image.setText("無圖片")
                self.btn_fav.setChecked(False)
                self.btn_fav.setText("收藏")
                self._current_cid = None
                return
            c = self.filtered[idx]
        else:
            if idx < 0 or idx >= len(self.filtered):
                return
            c = self.filtered[idx]

        cid, name, desc, ctype, atk, df, level, race, attr, setcode, alias, ot, category = c
        self._current_cid = cid

        # YGOPRODeck API 數據加載邏輯
        ygopro_data = self.ygoprodeck_cache.get(cid)
        ygopro_html = ""
        if isinstance(ygopro_data, dict):
            misc = ygopro_data.get("misc_info", [{}])[0]
            ban = ygopro_data.get("banlist_info", {})
            md_rarity = misc.get("md_rarity", "無")
            genesys_ocg_points = misc.get("genesys_ocg_points", "無")
            ban_ocg = ban.get("ban_ocg", "無限制")
            ban_tcg = ban.get("ban_tcg", "無限制")
            konami_id = misc.get("konami_id")
            
            ygopro_html = f"""
            <p style="color: #b388ff; margin: 2px 0;">MD 稀有度: {md_rarity} &nbsp;&nbsp;&nbsp;&nbsp; Genesys OCG 點數: {genesys_ocg_points}</p>
            <p style="color: #b388ff; margin: 2px 0;">OCG: {ban_ocg} &nbsp;&nbsp;&nbsp;&nbsp; TCG: {ban_tcg}</p>
            """
            
            self.btn_detail.setEnabled(True)
            if konami_id:
                self.btn_qa.setEnabled(True)
            else:
                self.btn_qa.setEnabled(False)
        elif ygopro_data == "fetching":
            ygopro_html = """
            <p style="color: #888888; margin: 2px 0;">⏳ [YGOPRODeck 數據載入中...]</p>
            """
            self.btn_qa.setEnabled(False)
            self.btn_detail.setEnabled(False)
        else:
            # Not fetched or failed
            ygopro_html = ""
            self.btn_qa.setEnabled(False)
            self.btn_detail.setEnabled(False)
            if ygopro_data is None:
                self.ygoprodeck_cache[cid] = "fetching"
                self.fetch_ygoprodeck_info(cid)

        folder = self.combo_folder.currentText()
        is_fav = self.fav_mgr.contains(folder, cid)
        self.btn_fav.setChecked(is_fav)
        self.btn_fav.setText("取消收藏" if is_fav else "收藏")

        lua_features = self._get_lua_features(cid, name, alias)
        if lua_features:
            features_html = '<div style="margin-top: 6px; margin-bottom: 6px;">' + \
                            ''.join(f'<p style="color: #b388ff; margin: 2px 0;">{feat}</p>' for feat in lua_features) + \
                            '</div>'
        else:
            features_html = ""

        img_path = os.path.join(os.path.dirname(__file__), "pics", f"{cid}.jpg")
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            pixmap = pixmap.scaled(200, 290, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if self.current_lf_label:
                limit = self.lflist.get_limit(cid, self.current_lf_label)
                if limit != 3:
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.Antialiasing)
                    colors = {0: QColor(220, 50, 50), 1: QColor(255, 180, 0), 2: QColor(50, 200, 50)}
                    color = colors.get(limit, QColor(128, 128, 128))
                    radius = min(pixmap.width(), pixmap.height()) // 10
                    if radius < 12:
                        radius = 12
                    x = 6
                    y = 6
                    painter.setPen(QPen(QColor(40, 40, 50), 1))
                    painter.setBrush(QBrush(color))
                    painter.drawEllipse(x, y, radius * 2, radius * 2)
                    painter.setPen(QPen(Qt.white, 1))
                    painter.setFont(QFont("Arial", radius, QFont.Bold))
                    texts = {0: "禁", 1: "限", 2: "準"}
                    painter.drawText(x, y, radius * 2, radius * 2, Qt.AlignCenter, texts.get(limit, ""))
                    painter.end()
            self.lbl_image.setPixmap(pixmap)
        else:
            self.lbl_image.setText("無圖片")

        is_magic = bool(ctype & TYPE_MAGIC)
        is_trap = bool(ctype & TYPE_TRAP)
        is_monster = bool(ctype & TYPE_MONSTER)

        type_parts = []
        if is_monster:
            type_parts.append("怪獸")
        if is_magic:
            type_parts.append("魔法")
        if is_trap:
            type_parts.append("陷阱")

        for t_mask, t_name in TYPE_CHINESE.items():
            if t_mask in [0x1, 0x2, 0x4, 0x1000000000000000, 0x2000000000000000, 0x4000000000000000, 0x8000000000000000]:
                continue
            if ctype & t_mask:
                type_parts.append(t_name)

        if ctype & 0x20000:  # TYPE_CONTINUOUS
            type_parts.append("永續")

        if ctype & 0x80:  # TYPE_RITUAL
            type_parts.append("儀式")

        final_types = []
        for t in type_parts:
            if t not in final_types:
                final_types.append(t)
        type_display = " / ".join(final_types) if final_types else "未知卡種"

        attr_display = ATTRIBUTE_MAP.get(attr, "")
        race_list = [v for k, v in RACE_MAP.items() if race & k]
        race_display = "、".join(race_list) if race_list else ""
        attr_race_row = ""
        if attr_display or race_display:
            parts = []
            if attr_display:
                parts.append(f"【{attr_display}屬性】")
            if race_display:
                parts.append(f"【{race_display}族】")
            attr_race_row = f'<p style="color: #00ffcc; margin: 2px 0; font-size: 13px;">{" ".join(parts)}</p>'

        archetypes = []
        temp_setcode = setcode if setcode is not None else 0
        for _ in range(4):
            sub_code = temp_setcode & 0xFFFF
            if sub_code in SETNAME_MAP:
                archetypes.append(SETNAME_MAP[sub_code])
            temp_setcode >>= 16
        archetypes = list(set(archetypes))
        setname_display = "、".join(archetypes) if archetypes else "無系列"

        category_names = []
        if category:
            for code, name2 in CATEGORY_MAP.items():
                if category & code:
                    category_names.append(name2)
        category_display = "、".join(category_names) if category_names else "無"
        category_row = f'<p style="color: #b388ff; margin: 2px 0;">效果分類: {category_display}</p>'

        limit_text = ""
        if self.current_lf_label:
            limit = self.lflist.get_limit(cid, self.current_lf_label)
            limit_map = {0: "禁止", 1: "限制", 2: "準限制", 3: "無限制"}
            limit_text = f"<p style='color: #ff8866;'>禁卡狀態: {limit_map.get(limit, '未知')}</p>"

        env_map = {1: "OCG", 2: "TCG", 3: "OCG & TCG", 4: "其他"}
        env_display = env_map.get(ot, "未知")

        is_link = bool(ctype & TYPE_LINK)
        is_spell_or_trap = bool(ctype & (TYPE_MAGIC | TYPE_TRAP))
        atk_display = '?' if atk == -2 else str(atk)
        lv_row = ""
        if is_link:
            arrows_found = []
            for mask, sym in ARROW_SYMBOLS.items():
                if df & mask:
                    arrows_found.append(f"[{sym}]")
            arrow_str = "".join(arrows_found)
            stat_row = f'<span style="color: #55aaff; font-weight: bold;">[LINK-{level & 0xFF}]</span> {atk_display}/- &nbsp;&nbsp;<span style="color: #ff9900;">{arrow_str}</span>'
        elif is_spell_or_trap:
            stat_row = ""
        else:
            def_display = '?' if df == -2 else str(df)
            stat_row = f'<p style="color: #e0e0e6; font-size: 13px; margin: 6px 0;">{atk_display}/{def_display}</p>'
            lv_row = f'<p style="color: #e0e0e6; margin: 2px 0;">★ 星等/階級: {level & 0xFFFF}</p>'
            if ctype & TYPE_PENDULUM:
                scale_val = (level >> 24) & 0xFF
                lv_row += f'<p style="color: #e0e0e6; margin: 2px 0;">靈擺刻度: {scale_val}</p>'

        title_str = name
        desc_str = desc if desc else "(無效果描述)"
        raw_key = self.search.text().strip()
        if raw_key:
            multi = self.chk_multi_keyword.isChecked()
            if multi:
                keywords = [kw.strip() for kw in raw_key.split() if kw.strip()]
                if keywords:
                    keywords.sort(key=len, reverse=True)
                    pattern = re.compile("|".join(map(re.escape, keywords)), re.IGNORECASE)
                    highlight_format = r'<span style="background-color: #ffcc00; color: #000000; font-weight: bold;">\g<0></span>'
                    title_str = pattern.sub(highlight_format, title_str)
                    desc_str = pattern.sub(highlight_format, desc_str)
            else:
                try:
                    pattern = re.compile(re.escape(raw_key), re.IGNORECASE)
                    highlight_format = r'<span style="background-color: #ffcc00; color: #000000; font-weight: bold;">\g<0></span>'
                    title_str = pattern.sub(highlight_format, title_str)
                    desc_str = pattern.sub(highlight_format, desc_str)
                except Exception:
                    pass

        related_html = ""
        if alias != 0:
            original_card = self.id_map.get(alias)
            if original_card:
                orig_id, orig_name, _, _, _, _, _, _, _, _, _, _, _ = original_card
                if orig_name == name:
                    relate_type = "異圖卡（同名異圖）"
                else:
                    relate_type = "規則上同名卡（效果/名稱視為原卡）"
                related_html += f'<p style="color: #88ddff; margin: 4px 0;"><b>關聯類型：</b>{relate_type}</p>'
                related_html += f'<p style="color: #88ddff; margin: 4px 0;"><b>原卡：</b>ID {str(orig_id).zfill(8)} - {orig_name}</p>'
            else:
                related_html += f'<p style="color: #ff8888; margin: 4px 0;">⚠️ 未找到 alias 對應的原卡 (ID: {str(alias).zfill(8)})</p>'

            related_cards = []
            related_cards.append((cid, name))
            for card in self.alias_index.get(cid, []):
                rc_id, rc_name, _, _, _, _, _, _, _, _, _, _, _ = card
                if rc_id != cid:
                    related_cards.append((rc_id, rc_name))
            if alias != cid:
                for card in self.alias_index.get(alias, []):
                    rc_id, rc_name, _, _, _, _, _, _, _, _, _, _, _ = card
                    if rc_id != cid:
                        related_cards.append((rc_id, rc_name))
            seen = set()
            unique_cards = []
            for rc_id, rc_name in related_cards:
                if rc_id not in seen:
                    seen.add(rc_id)
                    unique_cards.append((rc_id, rc_name))
            if len(unique_cards) > 1:
                related_html += '<p style="color: #88ddff; margin: 4px 0;"><b>關聯卡片清單：</b></p><ul style="color: #cccccc; margin: 2px 0; padding-left: 20px;">'
                for rc_id, rc_name in unique_cards:
                    marker = " ⬅️ 當前" if rc_id == cid else ""
                    related_html += f'<li>ID {str(rc_id).zfill(8)} - {rc_name}{marker}</li>'
                related_html += '</ul>'

        html_content = f"""
        <div style="line-height: 150%; padding-top: 10px;">
            <h2 style="margin-bottom: 5px;"><a href="copy:name" style="color: #00d2ff; text-decoration: none;">{title_str}</a></h2>
            <p style="margin: 2px 0;"><a href="copy:code" style="color: #a0a0aa; text-decoration: none;">卡片密碼: {str(cid).zfill(8)}</a> &nbsp;&nbsp;&nbsp;&nbsp; <span style="color: #99ff99;">[環境: {env_display}]</span></p>
            <p style="color: #ffd700; margin: 2px 0; font-size: 13px;"><b>卡片種類: {type_display}</b></p>
            {attr_race_row}
            <p style="color: #ff557f; margin: 2px 0;">所屬系列: {setname_display}</p>
            {category_row}
            {features_html}
            {limit_text}
            {stat_row}
            {lv_row}
            {ygopro_html}
            <hr style="border: 0; border-top: 1px solid #3a3a42; margin: 10px 0;">
            <p style="font-size: 12px;"><a href="copy:desc" style="color: #ffffff; text-decoration: none; white-space: pre-wrap;">{desc_str.replace('\n', '<br>')}</a></p>
            {related_html}
        </div>
        """
        self.info.setHtml(html_content)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Viewer()
    w.show()
    sys.exit(app.exec())