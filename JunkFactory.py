import sys
import os
import shutil
import time
import subprocess
import ctypes
import ctypes.wintypes
import struct
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from threading import Thread
from queue import Queue, Empty
from PIL import Image, ImageTk, ImageOps

def get_resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, 'resources', relative_path)

if sys.platform.startswith("win"):
    SYSTEM_DRIVE = os.path.splitdrive(os.getcwd())[0] or "C:"
    PROTECTED_DIRS = [
        os.path.abspath(os.path.join(SYSTEM_DRIVE, "Windows")),
        os.path.abspath(os.path.join(SYSTEM_DRIVE, "Windows", "System32")),
        os.path.abspath(SYSTEM_DRIVE + os.path.sep)
    ]
else:
    PROTECTED_DIRS = [
        os.path.abspath(os.path.sep),
        "/etc",
        "/usr",
        "/bin"
    ]
PROTECTED_DIRS = [os.path.normcase(p) for p in PROTECTED_DIRS]

INVALID_PATTERNS = ['..', '~', '|', '>', '<', '"', "'", '\x00']

def is_path_allowed(path: str) -> bool:
    try:
        abs_path = os.path.normcase(os.path.abspath(path))
    except Exception:
        return False

    for pat in INVALID_PATTERNS:
        if pat in path:
            return False

    for protected in PROTECTED_DIRS:
        if abs_path == protected or abs_path.startswith(protected + os.path.sep):
            return False
    return True

def create_sparse_file(path: str, size: int) -> bool:
    try:
        plat = sys.platform
        # Linux
        if plat.startswith("linux"):
            subprocess.check_call(["fallocate", "-n", "-l", str(size), path])
            return True

        # macOS/BSD
        if plat == "darwin" or "bsd" in plat:
            import fcntl
            fd = os.open(path, os.O_RDWR | os.O_CREAT)
            F_PREALLOCATE = 42
            F_ALLOCATECONTIG = 2
            F_ALLOCATEALL = 4

            class Fstore_t(ctypes.Structure):
                _fields_ = [
                    ("fst_flags", ctypes.c_uint32),
                    ("fst_posmode", ctypes.c_int32),
                    ("fst_offset", ctypes.c_uint64),
                    ("fst_length", ctypes.c_uint64),
                    ("fst_bytesalloc", ctypes.c_uint64)
                ]
            fst = Fstore_t()
            fst.fst_flags = F_ALLOCATECONTIG
            fst.fst_posmode = 0
            fst.fst_offset = 0
            fst.fst_length = size
            fst.fst_bytesalloc = 0

            try:
                fcntl.fcntl(fd, F_PREALLOCATE, fst)
            except OSError:
                fst.fst_flags = F_ALLOCATEALL
                try:
                    fcntl.fcntl(fd, F_PREALLOCATE, fst)
                except OSError:
                    os.close(fd)
                    return False
            os.ftruncate(fd, size)
            os.close(fd)
            return True

        # Windows
        if plat.startswith("win"):
            GENERIC_WRITE = 0x40000000
            CREATE_ALWAYS = 2
            FILE_ATTRIBUTE_NORMAL = 0x80
            INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

            handle = ctypes.windll.kernel32.CreateFileW(
                ctypes.c_wchar_p(path),
                GENERIC_WRITE,
                0, None,
                CREATE_ALWAYS,
                FILE_ATTRIBUTE_NORMAL,
                None
            )
            if handle == INVALID_HANDLE_VALUE:
                return False

            FSCTL_SET_SPARSE = 0x900c4
            bytes_returned = ctypes.wintypes.DWORD(0)

            res = ctypes.windll.kernel32.DeviceIoControl(
                handle,
                FSCTL_SET_SPARSE,
                None,
                0,
                None,
                0,
                ctypes.byref(bytes_returned),
                None
            )
            if res == 0:
                ctypes.windll.kernel32.CloseHandle(handle)
                return False

            # 设置文件大小
            high = ctypes.c_ulong((size >> 32) & 0xFFFFFFFF)
            low = ctypes.c_ulong(size & 0xFFFFFFFF)
            ret = ctypes.windll.kernel32.SetFilePointer(handle, low, ctypes.byref(high), 0)
            if ret == 0xFFFFFFFF:
                ctypes.windll.kernel32.CloseHandle(handle)
                return False
            res = ctypes.windll.kernel32.SetEndOfFile(handle)
            ctypes.windll.kernel32.CloseHandle(handle)
            if res == 0:
                return False
            return True

    except Exception as e:
        print(f"[Sparse] 创建稀疏文件失败：{e}")
    return False


class JunkGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("垃圾生成器")
        self.root.geometry("460x380")
        self.root.resizable(False, False)

        bg_color = "#1a1a1a"
        panel_color = "#262626"
        accent_color = "#76ff03"
        text_color = "#e0e0e0"
        btn_color = "#333333"
        btn_hover = "#505050"
        disabled_color = "#444444"

        style = ttk.Style(self.root)
        style.theme_use('clam')
        self.root.configure(bg=bg_color)

        default_font = ("Consolas", 10)
        header_font = ("Consolas", 20, "bold")

        style.configure("Panel.TFrame", background=panel_color)
        style.configure("TLabel", background=panel_color, foreground=text_color, font=default_font)
        style.configure("Header.TLabel", background=panel_color, foreground=accent_color, font=header_font)
        style.configure("TEntry", fieldbackground="#3c3c3c", foreground=text_color, font=default_font)
        style.configure("TCombobox", fieldbackground="#3c3c3c", foreground=text_color, font=default_font)
        style.configure("TButton", background=btn_color, foreground=text_color, font=default_font, relief="flat")
        style.map(
            "TButton",
            background=[('active', btn_hover), ('disabled', disabled_color)],
            relief=[('pressed', 'flat'), ('!pressed', 'flat')],
        )
        style.map(
            "TCombobox",
            fieldbackground=[('readonly', "#3c3c3c")],
            foreground=[('readonly', text_color)],
            selectbackground=[('readonly', btn_hover)],
            selectforeground=[('readonly', text_color)],
        )
        self.root.option_add('*TEntry.selectBackground', btn_hover)
        self.root.option_add('*TEntry.selectForeground', text_color)
        style.configure("Browse.TButton", foreground=accent_color, font=("Consolas", 10, "bold"), background=btn_color)
        style.map("Browse.TButton", background=[('active', btn_hover), ('disabled', disabled_color)])

        container = ttk.Frame(self.root, style="Panel.TFrame", padding=25)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(container, text="🗑️垃圾生成器", style="Header.TLabel")
        header.pack(pady=(0, 20))

        form = ttk.Frame(container, style="Panel.TFrame")
        form.pack(fill=tk.X, pady=(0, 15))
        form.columnconfigure(0, weight=0)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, weight=0)
        form.columnconfigure(3, weight=0)

        # 存放路径
        ttk.Label(form, text="存放路径:").grid(row=0, column=0, sticky="e", padx=6, pady=10)
        self.path_var = tk.StringVar()
        path_entry = ttk.Entry(form, textvariable=self.path_var, width=38)
        path_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=6)

        icon_path = get_resource_path(os.path.join('icons', 'folder.png'))
        icon_image = Image.open(icon_path).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)
        r, g, b, a = icon_image.split()
        green_layer = Image.new("RGBA", icon_image.size, "#76ff03")
        colored_icon = Image.composite(green_layer, icon_image, a)
        colored_icon.putalpha(a)
        self.folder_icon = ImageTk.PhotoImage(colored_icon)

        browse_btn = tk.Button(
            form,
            image=self.folder_icon,
            command=self.browse_path,
            bg=panel_color,
            activebackground=panel_color,
            borderwidth=0,
            highlightthickness=0,
            relief='flat',
        )
        browse_btn.grid(row=0, column=3, padx=(6, 0), pady=10)

        # 文件名
        ttk.Label(form, text="文件名:").grid(row=1, column=0, sticky="e", padx=6, pady=10)
        self.name_var = tk.StringVar(value="垃圾.bin")
        name_entry = ttk.Entry(form, textvariable=self.name_var, width=38)
        name_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Label(form, text="").grid(row=1, column=3)

        # 大小
        ttk.Label(form, text="大小:").grid(row=2, column=0, sticky="e", padx=6, pady=10)
        size_unit_frame = ttk.Frame(form, style="Panel.TFrame")
        size_unit_frame.grid(row=2, column=1, sticky="w", padx=(6, 0), columnspan=1)
        self.size_var = tk.StringVar(value="1")
        vcmd = (self.root.register(self.on_size_validate), '%P')
        size_entry = ttk.Entry(size_unit_frame, textvariable=self.size_var, width=12, validate='key', validatecommand=vcmd)
        size_entry.pack(side=tk.LEFT)
        self.unit_var = tk.StringVar(value="MB")
        unit_combo = ttk.Combobox(
            size_unit_frame, textvariable=self.unit_var,
            values=["B", "KB", "MB", "GB"],
            width=6, state="readonly"
        )
        unit_combo.pack(side=tk.LEFT, padx=(4, 0))

        # 稀疏开关
        self.use_sparse_var = tk.BooleanVar(value=True)
        sparse_check = ttk.Checkbutton(
            form, text="稀疏文件",
            variable=self.use_sparse_var,
            style="TCheckbutton",
        )
        sparse_check.grid(row=2, column=2, sticky="w", padx=6)

        # 进度条和按钮
        self.progress = ttk.Progressbar(container, orient='horizontal', mode='determinate')
        self.progress.pack(fill=tk.X, pady=(10, 12))
        self.generate_btn = ttk.Button(container, text="⚙️生成垃圾", command=self.start_generation)
        self.generate_btn.pack(pady=5)

        # 状态栏
        status_panel = ttk.Frame(container, style="Panel.TFrame")
        status_panel.pack(fill=tk.X, side=tk.BOTTOM, pady=(20, 0))
        self.status_var = tk.StringVar(value="状态: 就绪")
        status_label = ttk.Label(status_panel, textvariable=self.status_var, font=("Consolas", 9, "italic"))
        status_label.pack(side=tk.LEFT)

        self.path_var.trace_add('write', self.validate)
        self.name_var.trace_add('write', self.validate)
        self.unit_var.trace_add('write', self.validate)
        self.size_var.trace_add('write', self.validate)
        self.validate()

        author_label = ttk.Label(
            self.root,
            text="作者：qiyalammm",
            font=("Consolas", 8, "italic"),
            foreground="#777777",
            background=panel_color
        )
        author_label.place(relx=1.0, rely=1.0, x=-10, y=-10, anchor='se')

        # 用于线程与主线程通信的队列（进度）
        self.progress_queue = Queue()
        self.root.after(100, self.process_queue)

    def on_size_validate(self, proposed):
        if not proposed.strip():
            return True
        try:
            val = float(proposed)
            if val <= 0:
                return False
        except ValueError:
            return False
        self.root.after_idle(self.validate)
        return True

    def validate(self, *args):
        path = self.path_var.get().strip()
        try:
            valid = (
                path and
                is_path_allowed(path) and
                self.name_var.get().strip() and
                float(self.size_var.get()) > 0 and
                self.unit_var.get() in {"B", "KB", "MB", "GB"}
            )
        except Exception:
            valid = False
        self.generate_btn.config(state='normal' if valid else 'disabled')

    def browse_path(self):
        dirpath = filedialog.askdirectory()
        if dirpath and is_path_allowed(dirpath):
            self.path_var.set(dirpath)
        elif dirpath:
            messagebox.showerror("非法路径", "请选择允许写入的路径。")

    def start_generation(self):
        if self.generate_btn['state'] == 'disabled':
            return
        path = self.path_var.get().strip()
        if not is_path_allowed(path):
            messagebox.showerror("非法路径", "目标路径不允许写入，请选择其他目录。")
            return
        self.generate_btn.config(state='disabled')
        self.progress['value'] = 0
        self.status_var.set("状态: 生成中…")
        Thread(target=self._generate_file, daemon=True).start()

    def _has_enough_space(self, path, required_size):
        try:
            drive = os.path.splitdrive(os.path.abspath(path))[0] or path
            total, used, free = shutil.disk_usage(drive)
            return free >= required_size
        except Exception as e:
            print(f"检查磁盘空间时出错: {e}")
            return False

    def process_queue(self):
        try:
            while True:
                pct, status_text = self.progress_queue.get_nowait()
                self.progress['value'] = pct
                self.status_var.set(status_text)
                if pct >= 100:
                    self.generate_btn.config(state='normal')
        except Empty:
            pass
        self.root.after(100, self.process_queue)

    def _generate_file(self):
        try:
            total = float(self.size_var.get()) * {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}[self.unit_var.get()]
            total = int(total)
            written = 0
            step = 1024 * 1024
            path, fname = self.path_var.get().strip(), self.name_var.get().strip()

            base, ext = os.path.splitext(fname)
            candidate = fname
            index = 1
            while os.path.exists(os.path.join(path, candidate)):
                candidate = f"{base}{index}{ext}"
                index += 1
            target = os.path.join(path, candidate)

            if not self._has_enough_space(path, total):
                self.progress_queue.put((0, "状态: 空间不足，生成已取消"))
                messagebox.showwarning("空间不足", "生成失败：目标磁盘空间不足。")
                self.generate_btn.config(state='normal')
                return

            os.makedirs(path, exist_ok=True)
            sparse_start = time.time()
            sparse_ok = False
            if self.use_sparse_var.get():
                sparse_ok = create_sparse_file(target, total)
            sparse_elapsed = time.time() - sparse_start

            if sparse_ok and os.path.exists(target) and os.path.getsize(target) >= total:
                self.progress_queue.put((100, f"状态: 完成 ({candidate}) 稀疏耗时: {sparse_elapsed:.2f}s"))
                return

            if os.path.exists(target):
                try:
                    os.remove(target)
                except Exception:
                    pass

            empty_chunk = b'\0' * 1024
            start_time = time.time()
            last_pct = -1
            with open(target, 'wb') as f:
                while written < total:
                    chunk = min(step, total - written)
                    to_write = int(chunk)
                    full_chunks, remainder = divmod(to_write, 1024)
                    for _ in range(full_chunks):
                        f.write(empty_chunk)
                    if remainder:
                        f.write(b'\0' * remainder)
                    written += chunk
                    pct = int(written / total * 100)
                    if pct != last_pct:
                        elapsed = time.time() - start_time
                        speed = written / elapsed if elapsed > 0 else 0
                        remaining = total - written
                        eta = remaining / speed if speed > 0 else float('inf')
                        mb_s = speed / (1024 ** 2)
                        m, s = divmod(int(eta), 60)
                        status_text = f"状态: 生成中… {pct}% 速度: {mb_s:.2f}MB/s 剩余: {m:02d}:{s:02d}"
                        self.progress_queue.put((pct, status_text))
                        last_pct = pct

            duration = time.time() - start_time
            total_mb = total / (1024 ** 2)
            avg_speed = total_mb / duration if duration > 0 else 0
            self.progress_queue.put((100, f"状态: 完成 ({candidate}) 平均: {avg_speed:.2f}MB/s 耗时: {duration:.2f}s"))

        except Exception as e:
            self.progress_queue.put((0, "状态: 错误"))
            messagebox.showerror("错误", f"生成失败: {e}")
            self.generate_btn.config(state='normal')


if __name__ == "__main__":
    root = tk.Tk()
    app = JunkGeneratorApp(root)
    root.mainloop()