import os
import cv2
import time
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

DATASET_DIR = "dataset"

class DataCollectorApp:
    def __init__(self, window, window_title):
        self.window = window
        self.window.title(window_title)
        self.window.geometry("800x600")
        
        # Ensure base dataset dir exists
        os.makedirs(DATASET_DIR, exist_ok=True)
        
        # Layout top frame
        self.top_frame = tk.Frame(window)
        self.top_frame.pack(pady=15)
        
        tk.Label(self.top_frame, text="Sign Name:", font=("Arial", 14)).pack(side=tk.LEFT, padx=5)
        self.sign_entry = tk.Entry(self.top_frame, width=20, font=("Arial", 14))
        self.sign_entry.pack(side=tk.LEFT, padx=5)
        
        self.collect_btn = tk.Button(self.top_frame, text="Collect Data", 
                                     font=("Arial", 12, "bold"), bg="#4CAF50", fg="white", 
                                     command=self.start_collection)
        self.collect_btn.pack(side=tk.LEFT, padx=15)
        
        # Display feedback
        self.status_var = tk.StringVar()
        self.status_var.set("Ready. Enter sign name and press Collect Data.")
        self.status_label = tk.Label(window, textvariable=self.status_var, fg="blue", font=("Arial", 12))
        self.status_label.pack(pady=5)
        
        # Video label
        self.canvas = tk.Label(window, bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Init camera
        self.vid = cv2.VideoCapture(0)
        # Force hardware to 20 FPS if possible
        self.vid.set(cv2.CAP_PROP_FPS, 20)
        
        # State variables
        self.is_recording = False
        self.preparing = False
        self.frames_buffer = []
        
        self.record_duration = 4.0 # seconds
        self.record_start_time = 0
        self.prep_start_time = 0
        
        self.update_webcam()
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def start_collection(self):
        sign_name = self.sign_entry.get().strip().lower()
        if not sign_name:
            messagebox.showwarning("Warning", "Please enter a sign name!")
            return
            
        if self.is_recording or self.preparing:
            return
            
        self.current_sign = sign_name
        self.sign_dir = os.path.join(DATASET_DIR, sign_name)
        os.makedirs(self.sign_dir, exist_ok=True)
        
        # Give user a brief 2-second setup to position hands
        self.preparing = True
        self.prep_start_time = time.time()
        self.frames_buffer = []

    def update_webcam(self):
        ret, frame = self.vid.read()
        
        if ret:
            # Mirror effect for comfortable recording
            frame = cv2.flip(frame, 1)
            current_time = time.time()
            
            # Preparation phase (3, 2, 1)
            if self.preparing:
                elapsed = current_time - self.prep_start_time
                remain = 2.0 - elapsed
                if remain <= 0:
                    self.preparing = False
                    self.is_recording = True
                    self.record_start_time = time.time()
                    self.status_var.set(f"🔴 Recording '{self.current_sign}'!")
                else:
                    self.status_var.set(f"Get Ready... {int(remain)+1}")
                    cv2.putText(frame, f"Starting in {int(remain)+1}...", (50, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 3)
                                
            # Recording phase (4 seconds)
            elif self.is_recording:
                elapsed = current_time - self.record_start_time
                self.frames_buffer.append(frame.copy())
                
                # Draw visual REC indicator and timer
                cv2.circle(frame, (40, 40), 10, (0, 0, 255), -1)
                cv2.putText(frame, "REC", (60, 48), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                
                progress_text = f"Time: {elapsed:.1f} / 4.0s"
                cv2.putText(frame, progress_text, (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                if elapsed >= self.record_duration:
                    self.is_recording = False
                    self.save_video()
                    
            # Update canvas with RGB frame
            cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(cv2image)
            imgtk = ImageTk.PhotoImage(image=img)
            self.canvas.imgtk = imgtk
            self.canvas.configure(image=imgtk)
        
        # ~20 FPS display updating (50ms)
        self.window.after(50, self.update_webcam)
        
    def save_video(self):
        # 1. Look for existing files to find next numbering (vid1.mp4, vid2.mp4...)
        existing_files = [f for f in os.listdir(self.sign_dir) if f.startswith("vid") and f.endswith(".mp4")]
        max_id = 0
        for f in existing_files:
            try:
                # remove 'vid' and '.mp4' to get int
                num = int(f.replace("vid", "").replace(".mp4", ""))
                max_id = max(max_id, num)
            except ValueError:
                pass
                
        filename = f"vid{max_id + 1}.mp4"
        filepath = os.path.join(self.sign_dir, filename)
        
        if not self.frames_buffer:
            self.status_var.set("❌ Error: No frames were recorded.")
            return
            
        # 2. Setup video writer
        height, width, _ = self.frames_buffer[0].shape
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        # Calculate exactly how many frames per second was captured to keep speed 1:1
        actual_fps = len(self.frames_buffer) / 4.0
        
        out = cv2.VideoWriter(filepath, fourcc, actual_fps, (width, height))
        for f_frame in self.frames_buffer:
            out.write(f_frame)
        out.release()
        
        self.status_var.set(f"✅ Saved successfully: {filename} ({len(self.frames_buffer)} frames)")
        
    def on_closing(self):
        if self.vid and self.vid.isOpened():
            self.vid.release()
        self.window.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = DataCollectorApp(root, "Sign Language Dataset Collector")
    root.mainloop()
