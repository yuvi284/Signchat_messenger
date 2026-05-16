import os
import torch
import traceback
import sys

# Set Keras Backend to PyTorch (kept for compatibility if other parts use Keras/Torch)
os.environ["KERAS_BACKEND"] = "torch"

# Append current directory to path for local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from inference_lstm_sentence import LSTMRecognizer

class ISLProcessor:
    def __init__(self):
        self.recognizer = None
        self.last_frame_count = 0
        
        # Initialize Models
        self.log("Loading LSTM Sentence Model...")
        try:
            self.recognizer = LSTMRecognizer()
            self.log("SUCCESS: LSTM Sentence Model Loaded.")
        except Exception as e:
            self.log(f"ERROR: Failed to load LSTM model: {str(e)}")
            traceback.print_exc()

        self.check_hardware()

    def log(self, text):
        print(f"[ISLProcessor] {text}")

    def check_hardware(self):
        try:
            gpu_active = torch.cuda.is_available()
            if gpu_active:
                gpu_name = torch.cuda.get_device_name(0)
                self.log(f"Hardware Acceleration: GPU ({gpu_name}) Active")
            else:
                self.log("Hardware Acceleration: CPU (PyTorch CUDA not detected)")
        except Exception as e:
            self.log(f"Hardware Check Failed: {str(e)}")

    def process_video(self, video_path):
        """
        Processes a video file and returns the refined ISL sentence using LSTM.
        """
        if not self.recognizer:
            self.log("Error: Recognizer not initialized.")
            return ""

        if not os.path.exists(video_path):
             self.log(f"Error: Video path not found: {video_path}")
             return ""

        try:
            self.log(f"Processing video: {video_path}")
            
            import time
            start_t = time.time()
            
            pred_sentence = self.recognizer.predict_sentence(video_path)
            self.last_frame_count = getattr(self.recognizer, "last_frame_count", 0)
            
            end_t = time.time()
            self.log(f"Processing complete in {end_t - start_t:.2f}s")
            self.log(f"FINAL REFINED SENTENCE: {pred_sentence}")
            
            return pred_sentence

        except Exception as e:
            self.log(f"Error during conversion: {str(e)}")
            traceback.print_exc()
            return ""

if __name__ == "__main__":
    # Simple test block
    processor = ISLProcessor()
    print("ISLProcessor initialized successfully.")

