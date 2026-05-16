import os
import cv2
import pickle
import numpy as np
import mediapipe as mp
import glob
from collections import deque

# Set Keras Backend to PyTorch (Best for Windows/GPU)
os.environ["KERAS_BACKEND"] = "torch"
import keras

# Global Label Map
LABEL_MAP = {}

def load_label_map_from_file(file_path):
    """Loads label mapping from a text file (ID:Label)."""
    mapping = {}
    try:
        if not os.path.exists(file_path):
            print(f"[Warning] Label file not found: {file_path}")
            return mapping
            
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key, value = parts[0].strip(), parts[1].strip()
                    # Map both string and int keys for robust lookup
                    mapping[key] = value
                    if key.isdigit():
                        mapping[int(key)] = value
        
        print(f"[Info] Loaded {len(mapping)} labels from {os.path.basename(file_path)}")
        return mapping
    except Exception as e:
        print(f"[Error] Failed to load label map: {e}")
        return mapping

# Load labels immediately
# Assuming labels_dict.txt is in the project root found relative to this script or generic path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LABEL_FILE_PATH = os.path.join(BASE_DIR, 'labels_dict.txt')
LABEL_MAP = load_label_map_from_file(LABEL_FILE_PATH)

class SignLanguageInference:
    def __init__(self, model_root_dir='models/resnet_remove_complex_model', confidence_threshold=0.8):
        self.confidence_threshold = confidence_threshold
        
        # 1. Setup Mediapipe
        mp_holistic = mp.solutions.holistic
        mp_drawing = mp.solutions.drawing_utils
        mp_drawing_styles = mp.solutions.drawing_styles
        self.mp_holistic = mp_holistic
        self.mp_drawing = mp_drawing
        self.mp_drawing_styles = mp_drawing_styles
        
        self.holistic = self.mp_holistic.Holistic(
            static_image_mode=False,
            model_complexity=0,  # 0: Lite for maximum performance
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # Accuracy & Stability Params (Improved transition handling)
        self.alpha = 0.7
        self.prev_probs = None
        self.window = deque(maxlen=8)
        self.last_committed_word = None
        self.prev_majority = None
        self.stability_counter = 0

        # 2. Load Model & Label Encoder
        self.load_artifacts(model_root_dir)

    def reset_inference(self):
        """Resets the stability state for a new video or session."""
        self.prev_probs = None
        self.window.clear()
        self.last_committed_word = None
        self.prev_majority = None
        self.stability_counter = 0

    def load_artifacts(self, root_dir):
        """
        Automatically finds the latest model folder based on date and loads artifacts.
        """
        if not os.path.exists(root_dir):
            raise FileNotFoundError(f"Model directory not found: {root_dir}")

        # Find all date folders
        all_folders = [f for f in glob.glob(os.path.join(root_dir, "*")) if os.path.isdir(f)]
        if not all_folders:
            raise FileNotFoundError("No model folders found inside the root directory.")
        
        # Sort by name (YYYY-MM-DD) to get the latest
        latest_folder = sorted(all_folders)[-1]
        print(f"📂 Loading artifacts from: {latest_folder}")

        # Load Keras Model
        model_path = os.path.join(latest_folder, 'best_static_model.keras')
        self.model = keras.saving.load_model(model_path)
        print("✅ Model Loaded.")

        # Load Label Encoder
        le_path = os.path.join(latest_folder, 'label_encoder.pkl')
        with open(le_path, 'rb') as f:
            self.label_encoder = pickle.load(f)
        print(f"✅ Label Encoder Loaded. Classes: {self.label_encoder.classes_}")

    # =========================================================================
    #  FEATURE EXTRACTION (MUST MATCH createDataset_remove_complex.py EXACTLY)
    # =========================================================================
    
    def extract_hand_features(self, landmarks):
        if not landmarks:
            return np.zeros(63)
        
        points = np.array([[lm.x, lm.y, lm.z] for lm in landmarks.landmark])
        
        # Center to Wrist
        wrist = points[0]
        centered = points - wrist
        
        # Normalize Scale
        max_dist = np.max(np.linalg.norm(centered, axis=1))
        if max_dist < 1e-6: max_dist = 1.0
        
        normalized = centered / max_dist
        return normalized.flatten()

    def extract_body_features(self, pose_landmarks):
        if not pose_landmarks:
            return np.zeros(12)

        # Indices: 11 (L Shoulder), 12 (R Shoulder), 13 (L Elbow), 14 (R Elbow)
        left_sh = np.array([pose_landmarks.landmark[11].x, pose_landmarks.landmark[11].y, pose_landmarks.landmark[11].z])
        right_sh = np.array([pose_landmarks.landmark[12].x, pose_landmarks.landmark[12].y, pose_landmarks.landmark[12].z])
        
        center_point = (left_sh + right_sh) / 2
        body_width = np.linalg.norm(left_sh - right_sh)
        if body_width < 0.01: body_width = 1.0

        pose_features = []
        for idx in [11, 12, 13, 14]: 
            lm = pose_landmarks.landmark[idx]
            pt = np.array([lm.x, lm.y, lm.z])
            pose_features.append((pt - center_point) / body_width)
            
        return np.array(pose_features).flatten()

    # =========================================================================
    #  MAIN LOOP
    # =========================================================================

    def extract_single_frame(self, frame):
        """Extracts features from a single frame."""
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.holistic.process(img_rgb)
        return self.extract_features_from_results(results)

    def extract_features_from_results(self, results):
        """Extracts features from pre-processed MediaPipe results."""
        lh = self.extract_hand_features(results.left_hand_landmarks)
        rh = self.extract_hand_features(results.right_hand_landmarks)
        aux = self.extract_body_features(results.pose_landmarks)

        if not (np.all(lh == 0) and np.all(rh == 0)):
             return np.concatenate([lh, rh, aux])
        return None

    def process_results(self, results):
        """
        Processes MediaPipe results and returns a list of candidates if a stable sign is detected.
        Otherwise returns None.
        """
        feat = self.extract_features_from_results(results)
        if feat is not None:
            # Add batch dimension
            input_vector = np.expand_dims(feat, axis=0)
            probs = self.model.predict(input_vector, verbose=0)[0]
            
            # --- EMA Smoothing ---
            if self.prev_probs is None:
                self.prev_probs = probs
            else:
                self.prev_probs = self.alpha * self.prev_probs + (1 - self.alpha) * probs
            
            # --- Confidence Threshold ---
            conf = np.max(self.prev_probs)
            if conf < 0.60:
                return None
            
            top_idx = np.argmax(self.prev_probs)
            current_raw_class = self.label_encoder.inverse_transform([top_idx])[0]
            
            self.window.append(current_raw_class)
            
            if len(self.window) == 8:
                # Layer 1: Window Majority
                majority_raw = max(set(self.window), key=list(self.window).count)
                
                # Layer 2: Consecutive Majority Stability
                if majority_raw == self.prev_majority:
                    self.stability_counter += 1
                else:
                    self.prev_majority = majority_raw
                    self.stability_counter = 1
                
                if self.stability_counter >= 8:
                    # Translate to human-readable label
                    human_label = LABEL_MAP.get(majority_raw, str(majority_raw))
                    
                    # Only commit if it's a new word
                    if human_label != self.last_committed_word:
                        top_6_indices = np.argsort(self.prev_probs)[-6:][::-1]
                        candidates = []
                        for idx in top_6_indices:
                            raw_class = self.label_encoder.inverse_transform([idx])[0]
                            label = LABEL_MAP.get(raw_class, str(raw_class))
                            candidates.append({
                                "label": label,
                                "accuracy": float(self.prev_probs[idx])
                            })
                        
                        self.last_committed_word = human_label
                        self.stability_counter = 0 # Reset Layer 2
                        print(f"  [DEBUG] ResNet Committed: {human_label} (Conf: {conf:.2f})")
                        return candidates
                    
                    self.stability_counter = 0 # Reset Layer 2
        return None

    def predict_video(self, video_path):
        """Processes a video and returns a list of stable detections (Top 6 each) using double-layer stability."""
        cap = cv2.VideoCapture(video_path)
        stable_detections = []
        
        self.reset_inference()
        
        print(f"\n[DEBUG] ResNet Processing video (EMA + Double Stability): {os.path.basename(video_path)}")
        import time
        start_time = time.time()
        while cap.isOpened():
            if time.time() - start_time > 30:
                print("[DEBUG] ResNet Processing timed out after 30 seconds.")
                break
                
            ret, frame = cap.read()
            if not ret: break
            
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.holistic.process(img_rgb)

            candidates = self.process_results(results)
            if candidates:
                stable_detections.append(candidates)
        
        cap.release()
        return stable_detections

    # =========================================================================
    #  MAIN LOOP
    # =========================================================================

    def run(self):
        cap = cv2.VideoCapture(0)
        
        print("📷 Webcam started. Press 'q' to quit.")

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # Flip and convert to RGB
            image = cv2.flip(frame, 1)
            
            # Extract Features
            feat = self.extract_single_frame(image)

            # Check if any hands are detected before predicting
            if feat is not None:
                # Create Input Vector (1, 138)
                input_vector = np.expand_dims(feat, axis=0)

                # Prediction
                prediction = self.model.predict(input_vector, verbose=0)
                predicted_index = np.argmax(prediction)
                confidence = prediction[0][predicted_index]

                # Display Logic
                if confidence > self.confidence_threshold:
                    raw_class = self.label_encoder.inverse_transform([predicted_index])[0]
                    predicted_class = LABEL_MAP.get(raw_class, str(raw_class))
                    
                    # Display Text
                    text = f"{predicted_class} ({confidence:.2f})"
                    cv2.rectangle(image, (0,0), (300, 60), (0,0,0), -1)
                    cv2.putText(image, text, (20, 40), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
                else:
                    # Low confidence display
                    cv2.putText(image, "...", (20, 40), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)
            else:
                cv2.putText(image, "No Hands Detected", (20, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            cv2.imshow('Sign Language Recognition', image)

            if cv2.waitKey(5) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

def load_labels_from_data(data_dir='./data'):
    global LABEL_MAP
    # Search for data folder in multiple locations
    search_paths = [
        data_dir,
        './data',
        '../sign-language-detecter-old/data',
        'F:/yugesh/ISL_projects/sign-language-detecter-old/data'
    ]
    
    found_dir = None
    for path in search_paths:
        if os.path.exists(path) and os.path.isdir(path):
            found_dir = path
            break
    
    if not found_dir:
        return
    
    data_dir = found_dir
    
    # print("📂 Scanning data folder for labels...")
    for folder_name in os.listdir(data_dir):
        folder_path = os.path.join(data_dir, folder_name)
        if os.path.isdir(folder_path):
            images = os.listdir(folder_path)
            if images:
                first_img = images[0]
                class_name = first_img.split('_')[0]
                
                LABEL_MAP[folder_name] = class_name
                try:
                    LABEL_MAP[int(folder_name)] = class_name
                except:
                    pass
    # print(f"✅ Loaded {len(LABEL_MAP)//2} labels from data folder.")

def get_inference_model():
    root_dir = 'models/resnet_remove_complex_model'
    if os.path.exists(root_dir):
        import glob
        all_folders = [f for f in glob.glob(os.path.join(root_dir, "*")) if os.path.isdir(f)]
        if all_folders:
            # Sort by name (YYYY-MM-DD) to get the latest is okay, but using getmtime is safer
            latest_folder = max(all_folders, key=os.path.getmtime)
            load_labels_from_data()
            return SignLanguageInference(model_root_dir=root_dir) # SignLanguageInference will find the latest itself
    return None

if __name__ == "__main__":
    load_labels_from_data()
    app = get_inference_model()
    if app:
        app.run()
    else:
        print("No model found.")
