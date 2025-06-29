import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import subprocess
from PIL import Image, ImageTk
import threading
import time
import random
import winreg
import sys # sys 모듈 추가

class PhotoWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("포토위젯")
        
        # 설정 파일 경로 및 설정 로드 (가장 먼저)
        # 사용자 AppData 로컬 폴더에 설정 파일을 저장하도록 변경
        app_data_path = os.path.join(os.environ['LOCALAPPDATA'], "PhotoWidget")
        if not os.path.exists(app_data_path):
            os.makedirs(app_data_path)
        self.config_file = os.path.join(app_data_path, "photo_widget_config.json")
        # ---------------------------

        self.config = self.load_config()
        
        # 위치 잠금 상태 초기화 (UI 생성 전에 먼저)
        self.position_locked = self.config.get('position_locked', False)
        
        # 숨겨진 상태 관리 초기화
        self.is_hidden = False
        
        # 설정에서 크기와 위치 불러오기
        width = self.config.get('width', 300)
        height = self.config.get('height', 200)
        x = self.config.get('x', None)
        y = self.config.get('y', None)
        
        # 위치가 저장되어 있지 않으면 우하단으로
        if x is None or y is None:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = screen_width - width - 20
            y = screen_height - height - 70
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # 바탕화면 위젯처럼 설정
        self.root.wm_attributes('-topmost', False)  # 항상 위가 아닌 바탕화면 레벨
        self.root.overrideredirect(True)  # 타이틀바 제거
        self.root.attributes('-alpha', self.config.get('alpha', 0.9))  # 투명도
        self.root.configure(bg='black')  # 검은색 배경
        
        # 지원하는 이미지 확장자
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        
        # 현재 이미지 목록과 인덱스
        self.image_files = []
        self.current_index = 0
        self.current_image = None
        
        # 툴팁 초기화
        self.tooltip = None
        
        # UI 생성
        self.create_ui()
        
        # 드래그 이동 가능하게 설정 (UI 생성 후)
        self.setup_drag_move()
        
        # 폴더가 설정되어 있으면 이미지 로드
        if self.config.get('folder_path'):
            self.load_images()
            self.start_slideshow()
    
    def create_ui(self):
        # 메인 프레임
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 이미지 표시 레이블 (검은색 배경)
        self.image_label = tk.Label(main_frame, text="폴더를 선택해주세요", 
                                   bg='black', fg='white', font=('Arial', 10))
        self.image_label.pack(fill=tk.BOTH, expand=True)
        
        # 크기 조절 핸들 생성
        self.create_resize_handles()
        
        # 위치 잠금 아이콘 추가
        self.create_lock_icon()
        
        # 이벤트 바인딩
        self.image_label.bind("<Double-Button-1>", self.open_current_image)
        
        # 우클릭 메뉴 (타이틀바가 없으므로 중요)
        self.root.bind("<Button-3>", self.show_context_menu)
        self.image_label.bind("<Button-3>", self.show_context_menu)
        
        # 컨텍스트 메뉴
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="폴더 선택", command=self.select_folder)
        self.context_menu.add_command(label="설정", command=self.open_settings)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="위치 잠금/해제", command=self.toggle_position_lock)
        self.context_menu.add_command(label="위젯 숨기기", command=self.hide_widget)
        self.context_menu.add_command(label="종료", command=self.root.quit)
    
    def setup_drag_move(self):
        """위젯을 드래그로 이동할 수 있게 설정"""
        self.start_x = 0
        self.start_y = 0
        
        def start_move(event):
            if self.position_locked:
                return
            self.start_x = event.x
            self.start_y = event.y
        
        def do_move(event):
            if self.position_locked:
                return
            x = self.root.winfo_x() + (event.x - self.start_x)
            y = self.root.winfo_y() + (event.y - self.start_y)
            self.root.geometry(f"+{x}+{y}")
        
        # 이미지 레이블에서 드래그 가능
        self.image_label.bind("<Button-1>", start_move)
        self.image_label.bind("<B1-Motion>", do_move)
    
    def create_lock_icon(self):
        """위치 잠금 아이콘 생성"""
        # 잠금 아이콘 (우상단)
        self.lock_icon = tk.Label(self.root, 
                                 bg='black', fg='white', 
                                 font=('Arial', 12),
                                 cursor='hand2')
        self.lock_icon.place(relx=1.0, rely=0.0, anchor='ne', x=-5, y=5)
        
        # 잠금 상태에 따라 아이콘 업데이트
        self.update_lock_icon()
        
        # 클릭 이벤트
        self.lock_icon.bind("<Button-1>", lambda e: self.toggle_position_lock())
        
        # 마우스 오버 효과
        def on_enter(event):
            self.lock_icon.configure(bg='gray')
        
        def on_leave(event):
            self.lock_icon.configure(bg='black')
        
        self.lock_icon.bind("<Enter>", on_enter)
        self.lock_icon.bind("<Leave>", on_leave)
    
    def update_lock_icon(self):
        """잠금 상태에 따라 아이콘 업데이트"""
        if self.position_locked:
            self.lock_icon.configure(text="🔒", fg='red')
        else:
            self.lock_icon.configure(text="🔓", fg='white')
    
    def toggle_position_lock(self):
        """위치 잠금 토글"""
        self.position_locked = not self.position_locked
        self.config['position_locked'] = self.position_locked
        self.update_lock_icon()
        self.save_config()
        
        # 잠금 상태 변경시 크기 조절 핸들도 활성화/비활성화
        if self.position_locked:
            self.resize_handle.configure(state='disabled', cursor='')
        else:
            self.resize_handle.configure(state='normal', cursor='bottom_right_corner')
    
    def create_resize_handles(self):
        """크기 조절 핸들 생성"""
        # 우하단 크기 조절 핸들
        self.resize_handle = tk.Label(self.root, text="⋱", 
                                    bg='gray', fg='white', 
                                    font=('Arial', 8),
                                    cursor='bottom_right_corner')
        self.resize_handle.place(relx=1.0, rely=1.0, anchor='se', x=-2, y=-2)
        
        # 크기 조절 변수
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_start_width = 0
        self.resize_start_height = 0
        
        def do_resize(event):
            if self.position_locked:
                return
            # 마우스 이동 거리 계산
            delta_x = event.x_root - self.resize_start_x
            delta_y = event.y_root - self.resize_start_y
            
            # 새로운 크기 계산 (최소 크기 제한)
            new_width = max(200, self.resize_start_width + delta_x)
            new_height = max(150, self.resize_start_height + delta_y)
            
            # 크기 조절
            self.root.geometry(f"{new_width}x{new_height}")
            
            # 현재 이미지가 있다면 다시 표시 (크기에 맞게 조정)
            if self.current_image:
                self.display_image(self.current_image)
        
        def start_resize(event):
            if self.position_locked:
                return
            self.resize_start_x = event.x_root
            self.resize_start_y = event.y_root
            self.resize_start_width = self.root.winfo_width()
            self.resize_start_height = self.root.winfo_height()
        
        # 크기 조절 핸들에 이벤트 바인딩
        self.resize_handle.bind("<Button-1>", start_resize)
        self.resize_handle.bind("<B1-Motion>", do_resize)
        
        # 마우스 오버시 핸들 강조
        def on_enter(event):
            self.resize_handle.configure(bg='lightgray')
        
        def on_leave(event):
            self.resize_handle.configure(bg='gray')
        
        self.resize_handle.bind("<Enter>", on_enter)
        self.resize_handle.bind("<Leave>", on_leave)
    
    def hide_widget(self):
        """위젯 숨기기/보이기"""
        if self.is_hidden:
            self.root.deiconify()
            self.is_hidden = False
        else:
            self.root.withdraw()
            self.is_hidden = True
            # 5초 후 자동으로 다시 보이기
            self.root.after(5000, lambda: self.show_widget())
    
    def load_config(self):
        """설정 파일 로드"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"설정 파일 로드 실패: {e}")
        
        # 기본 설정 반환
        return {
            'folder_path': '',
            'auto_start': False,
            'slideshow_interval': 5,
            'width': 300,
            'height': 200,
            'x': None,
            'y': None,
            'alpha': 0.9,
            'position': '우하단',
            'position_locked': False
        }
    
    def save_config(self):
        """설정 파일 저장"""
        try:
            # 현재 위치와 크기 저장
            geometry = self.root.geometry()
            # geometry 형식: "widthxheight+x+y"
            size_pos = geometry.split('+')
            if len(size_pos) >= 3:
                width_height = size_pos[0].split('x')
                if len(width_height) == 2:
                    self.config['width'] = int(width_height[0])
                    self.config['height'] = int(width_height[1])
                    self.config['x'] = int(size_pos[1])
                    self.config['y'] = int(size_pos[2])
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("오류", f"설정 저장 실패: {e}")
    
    def select_folder(self):
        """폴더 선택"""
        folder = filedialog.askdirectory(title="사진 폴더 선택")
        if folder:
            self.config['folder_path'] = folder
            self.save_config()
            self.load_images()
            self.start_slideshow()
    
    def load_images(self):
        """폴더에서 이미지 파일 로드"""
        self.image_files = []
        folder_path = self.config.get('folder_path')
        
        if not folder_path or not os.path.exists(folder_path):
            return
        
        # 폴더와 하위폴더에서 이미지 파일 검색
        for root_dir, dirs, files in os.walk(folder_path):
            for file in files:
                if os.path.splitext(file.lower())[1] in self.image_extensions:
                    self.image_files.append(os.path.join(root_dir, file))
        
        if self.image_files:
            random.shuffle(self.image_files)  # 랜덤 순서로 섞기
            print(f"로드된 이미지 파일 수: {len(self.image_files)}")
    
    def display_image(self, image_path):
        """이미지 표시"""
        try:
            # 이미지 로드 및 리사이즈
            image = Image.open(image_path)
            
            # 위젯 크기에 맞게 조정
            widget_width = self.root.winfo_width()
            widget_height = self.root.winfo_height()
            
            if widget_width <= 1 or widget_height <= 1:
                widget_width = self.config.get('width', 300)
                widget_height = self.config.get('height', 200)
            
            image.thumbnail((widget_width, widget_height), Image.Resampling.LANCZOS)
            
            # tkinter용 이미지로 변환
            photo = ImageTk.PhotoImage(image)
            
            # 이미지 표시
            self.image_label.configure(image=photo, text="")
            self.image_label.image = photo  # 참조 유지
            self.current_image = image_path
            
        except Exception as e:
            print(f"이미지 로드 실패: {image_path}, 오류: {e}")
            self.next_image()
    
    def next_image(self):
        """다음 이미지로 이동"""
        if not self.image_files:
            return
        
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self.display_image(self.image_files[self.current_index])
    
    def start_slideshow(self):
        """슬라이드쇼 시작"""
        def slideshow_loop():
            while True:
                if self.image_files and not self.is_hidden:
                    self.root.after(0, self.next_image)
                time.sleep(self.config.get('slideshow_interval', 5))
        
        if self.image_files:
            self.display_image(self.image_files[0])
            threading.Thread(target=slideshow_loop, daemon=True).start()
    
    def open_current_image(self, event):
        """현재 이미지를 기본 프로그램으로 열기"""
        if self.current_image and os.path.exists(self.current_image):
            try:
                os.startfile(self.current_image)
            except Exception as e:
                messagebox.showerror("오류", f"이미지 열기 실패: {e}")
    
    def show_tooltip(self, event):
        """마우스 오버시 툴팁 표시"""
        if self.current_image:
            self.tooltip = tk.Toplevel(self.root)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
            
            # 파일명만 표시 (전체 경로가 아닌)
            filename = os.path.basename(self.current_image)
            label = ttk.Label(self.tooltip, text=filename, 
                            background="lightyellow", relief="solid", borderwidth=1)
            label.pack()
    
    def hide_tooltip(self, event):
        """툴팁 숨기기"""
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None
    
    def show_widget(self):
        """위젯 다시 보이기"""
        if self.is_hidden:
            self.root.deiconify()
            self.is_hidden = False
    
    def show_context_menu(self, event):
        """컨텍스트 메뉴 표시"""
        try:
            self.context_menu.post(event.x_root, event.y_root)
        except:
            pass
    
    def open_settings(self):
        """설정 창 열기"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("설정")
        settings_window.geometry("400x450")
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        # 폴더 경로 설정
        ttk.Label(settings_window, text="사진 폴더:").pack(pady=5)
        folder_frame = ttk.Frame(settings_window)
        folder_frame.pack(fill=tk.X, padx=20, pady=5)
        
        folder_var = tk.StringVar(value=self.config.get('folder_path', ''))
        folder_entry = ttk.Entry(folder_frame, textvariable=folder_var, state='readonly')
        folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(folder_frame, text="찾아보기", 
                  command=lambda: self.browse_folder(folder_var)).pack(side=tk.RIGHT, padx=(5, 0))
        
        # 슬라이드쇼 간격 설정
        ttk.Label(settings_window, text="슬라이드쇼 간격 (초):").pack(pady=(20, 5))
        interval_var = tk.IntVar(value=self.config.get('slideshow_interval', 5))
        interval_spin = ttk.Spinbox(settings_window, from_=1, to=60, textvariable=interval_var)
        interval_spin.pack(pady=5)
        
        # 위젯 위치 설정
        ttk.Label(settings_window, text="위젯 위치:").pack(pady=(20, 5))
        position_frame = ttk.Frame(settings_window)
        position_frame.pack(pady=5)
        
        position_var = tk.StringVar(value=self.config.get('position', '우하단'))
        positions = ['우하단', '우상단', '좌하단', '좌상단', '중앙']
        position_combo = ttk.Combobox(position_frame, textvariable=position_var, 
                                    values=positions, state='readonly')
        position_combo.pack(side=tk.LEFT)
        
        ttk.Button(position_frame, text="적용", 
                  command=lambda: self.set_position(position_var.get())).pack(side=tk.LEFT, padx=(5, 0))
        
        # 투명도 설정
        ttk.Label(settings_window, text="투명도:").pack(pady=(10, 5))
        alpha_var = tk.DoubleVar(value=self.config.get('alpha', 0.9))
        alpha_scale = ttk.Scale(settings_window, from_=0.3, to=1.0, 
                              variable=alpha_var, orient=tk.HORIZONTAL)
        alpha_scale.pack(pady=5)
        
        def update_alpha(event=None):
            self.root.attributes('-alpha', alpha_var.get())
        alpha_scale.bind("<Motion>", update_alpha)
        
        # 자동 시작 설정
        auto_start_var = tk.BooleanVar(value=self.config.get('auto_start', False))
        ttk.Checkbutton(settings_window, text="윈도우 시작시 자동 실행", 
                       variable=auto_start_var).pack(pady=10)
        
        # 버튼
        button_frame = ttk.Frame(settings_window)
        button_frame.pack(pady=20)
        
        def save_settings():
            self.config['folder_path'] = folder_var.get()
            self.config['slideshow_interval'] = interval_var.get()
            self.config['auto_start'] = auto_start_var.get()
            self.config['position'] = position_var.get()
            self.config['alpha'] = alpha_var.get()
            
            # 자동 시작 레지스트리 설정
            self.set_auto_start(auto_start_var.get())
            
            # 투명도 적용
            self.root.attributes('-alpha', alpha_var.get())
            
            self.save_config()
            
            # 폴더가 변경되었으면 이미지 다시 로드
            self.load_images()
            
            settings_window.destroy()
            messagebox.showinfo("설정", "설정이 저장되었습니다.")
        
        ttk.Button(button_frame, text="저장", command=save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="취소", command=settings_window.destroy).pack(side=tk.LEFT, padx=5)
    
    def set_position(self, position):
        """위젯 위치 설정"""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        widget_width = self.config.get('width', 300)
        widget_height = self.config.get('height', 200)
        
        positions = {
            '우하단': (screen_width - widget_width - 20, screen_height - widget_height - 70),
            '우상단': (screen_width - widget_width - 20, 20),
            '좌하단': (20, screen_height - widget_height - 70),
            '좌상단': (20, 20),
            '중앙': ((screen_width - widget_width) // 2, (screen_height - widget_height) // 2)
        }
        
        if position in positions:
            x, y = positions[position]
            self.root.geometry(f"{widget_width}x{widget_height}+{x}+{y}")
    
    def browse_folder(self, folder_var):
        """폴더 선택 다이얼로그"""
        folder = filedialog.askdirectory(title="사진 폴더 선택")
        if folder:
            folder_var.set(folder)
    def set_auto_start(self, enable):
        """윈도우 자동 시작 설정"""
        try:
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)

            if enable:
                # 여기에 직접 .exe 파일의 고정된 경로를 입력합니다.
                # 예시:
                # exe_path = r"C:\PhotoWidget\photo_widget_v6.exe"
                # 또는
                # 프로그램이 설치되는 경로를 기준으로 설정 (더 유연함)
                # 만약 PyInstaller로 실행 파일을 만들고,
                # 이 코드가 그 실행 파일 안에서 실행된다면 아래처럼 사용 가능:
                exe_path = os.path.abspath(sys.argv[0]) # 현재 실행 중인 .exe 파일의 경로

                winreg.SetValueEx(key, "PhotoWidget", 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, "PhotoWidget")
                except FileNotFoundError:
                    pass

            winreg.CloseKey(key)
        except Exception as e:
            messagebox.showerror("오류", f"자동 시작 설정 실패: {e}\n관리자 권한으로 실행했는지 확인해주세요.")
        
    def run(self):
        """프로그램 실행"""
        try:
            self.root.mainloop()
        finally:
            # 프로그램 종료시 설정 저장
            self.save_config()

if __name__ == "__main__":
    # 필요한 라이브러리 확인
    try:
        import PIL
    except ImportError:
        import tkinter.messagebox as mb
        mb.showerror("오류", "Pillow 라이브러리가 필요합니다.\n\npip install Pillow 명령으로 설치해주세요.")
        exit(1)
    
    app = PhotoWidget()
    app.run()