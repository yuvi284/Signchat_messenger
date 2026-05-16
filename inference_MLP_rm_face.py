import cv2
import mediapipe as mp
import numpy as np
import pickle
import os
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
# Try absolute path based on user context, or relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Fallback to known project root if needed, but relative is safer if structure is consistent
# User file: f:\yugesh\ISL_projects\sign_language_app_20-1-26\labels_dict.txt
LABEL_FILE_PATH = os.path.join(BASE_DIR, 'labels_dict.txt')
LABEL_MAP = load_label_map_from_file(LABEL_FILE_PATH)

class SignLanguageInference:
    def __init__(self, model_dir, threshold=0.7):
        """
        model_dir: Path to the specific date folder (e.g., 'models/face_remove_model/2023-10-27')
        threshold: Confidence threshold for displaying predictions
        """
        self.threshold = threshold
        
        # 1. Load Model and Label Encoder
        model_path = os.path.join(model_dir, 'final_sign_language_model.keras')
        label_path = os.path.join(model_dir, 'label_encoder.pkl')

        if not os.path.exists(model_path) or not os.path.exists(label_path):
            raise FileNotFoundError(f"Artifacts not found in {model_dir}. Check paths.")

        print(f"Loading model from: {model_path}")
        print(f"Loading model from: {model_path}")
        
        # Custom classes to handle version mismatch (ignore quantization_config)
        class FixedDense(keras.layers.Dense):
            @classmethod
            def from_config(cls, config):
                if 'quantization_config' in config:
                    config.pop('quantization_config')
                return super().from_config(config)

        class FixedDropout(keras.layers.Dropout):
            @classmethod
            def from_config(cls, config):
                if 'quantization_config' in config:
                    config.pop('quantization_config')
                return super().from_config(config)

        self.model = keras.saving.load_model(model_path, custom_objects={
            'Dense': FixedDense,
            'Dropout': FixedDropout
        })
        
        with open(label_path, 'rb') as f:
            self.label_encoder = pickle.load(f)
        
        self.classes = self.label_encoder.classes_
        print(f"Loaded Classes: {self.classes}")

        # 2. Initialize MediaPipe
        import mediapipe as mp
        mp_holistic = mp.solutions.holistic
        mp_drawing = mp.solutions.drawing_utils
        
        self.mp_holistic = mp_holistic
        self.mp_drawing = mp_drawing
        self.holistic = self.mp_holistic.Holistic(
            model_complexity=0,  # 0: Lite, 1: Full, 2: Heavy. Lite is much faster for real-time.
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

    def reset_inference(self):
        """Resets the stability state for a new video or session."""
        self.prev_probs = None
        self.window.clear()
        self.last_committed_word = None
        self.prev_majority = None
        self.stability_counter = 0

    # =========================================================================
    #  FEATURE EXTRACTION LOGIC (Must Match createdataset_face_remove.py)
    # =========================================================================

    def get_angle(self, a, b, c):
        """Calculates angle at vertex b (0-180 degrees)."""
        v1 = a - b
        v2 = c - b
        cosine = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
        angle = np.arccos(np.clip(cosine, -1.0, 1.0))
        return np.degrees(angle)

    def get_palm_normal(self, points):
        """Calculates the normal vector of the palm."""
        v1 = points[5] - points[0]
        v2 = points[17] - points[0]
        normal = np.cross(v1, v2)
        return normal / (np.linalg.norm(normal) + 1e-6)

    def extract_hand_features(self, landmarks, reference_point):
        """Extracts 88 features for a SINGLE hand."""
        if not landmarks:
            return np.zeros(88)

        points = np.array([[lm.x, lm.y, lm.z] for lm in landmarks.landmark])
        wrist = points[0]
        
        # 1. Geometry & Scale
        centered = points - wrist
        hand_size = np.linalg.norm(centered[9]) + 1e-6 
        normalized_pos = (centered / hand_size).flatten() 

        # 2. Bend Angles
        bend_angles = []
        bend_angles.append(self.get_angle(points[1], points[2], points[3]))
        bend_angles.append(self.get_angle(points[2], points[3], points[4]))
        bend_angles.append(self.get_angle(points[3], points[4], points[8])) 
        for i in [5, 9, 13, 17]:
            bend_angles.append(self.get_angle(points[0], points[i], points[i+1]))
            bend_angles.append(self.get_angle(points[i], points[i+1], points[i+2]))
            bend_angles.append(self.get_angle(points[i+1], points[i+2], points[i+3]))

        # 3. Spread Angles
        spread_angles = []
        spread_angles.append(self.get_angle(points[5], points[0], points[9]))   
        spread_angles.append(self.get_angle(points[9], points[0], points[13]))  
        spread_angles.append(self.get_angle(points[13], points[0], points[17])) 
        spread_angles.append(self.get_angle(points[4], points[0], points[5]))   

        # 4. Global Context
        if reference_point is not None:
            global_pos = (wrist - reference_point) / hand_size
        else:
            global_pos = np.array([0, 0, 0])

        # 5. Palm Normal
        palm_normal = self.get_palm_normal(points)

        features = np.concatenate([
            normalized_pos, bend_angles, spread_angles, global_pos, palm_normal
        ])
        if len(features) != 88: features = np.resize(features, 88)
        return features

    def extract_body_features(self, pose_landmarks, reference_point):
        """Extracts 12 features normalized by Body Scale (Shoulders/Elbows only)."""
        if reference_point is None:
            return np.zeros(12)

        # Body Scale
        body_scale = 1.0
        if pose_landmarks:
            left_sh = np.array([pose_landmarks.landmark[11].x, pose_landmarks.landmark[11].y, pose_landmarks.landmark[11].z])
            right_sh = np.array([pose_landmarks.landmark[12].x, pose_landmarks.landmark[12].y, pose_landmarks.landmark[12].z])
            width = np.linalg.norm(left_sh - right_sh)
            if width > 0.01: body_scale = width

        # Pose XYZ
        pose_features = []
        if pose_landmarks:
            for idx in [11, 12, 13, 14]: 
                lm = pose_landmarks.landmark[idx]
                pt = np.array([lm.x, lm.y, lm.z])
                pose_features.append((pt - reference_point) / body_scale)
            pose_flat = np.array(pose_features).flatten()
        else:
            pose_flat = np.zeros(12)

        return pose_flat

    # =========================================================================
    #  INFERENCE LOOP
    # =========================================================================

    def extract_single_frame(self, frame):
        """Extracts features from a single frame."""
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.holistic.process(img_rgb)
        return self.extract_features_from_results(results)

    def extract_features_from_results(self, results):
        """Extracts features from pre-processed MediaPipe results."""
        reference_point = None
        if results.pose_landmarks:
            nose = results.pose_landmarks.landmark[0]
            if nose.visibility > 0.5:
                reference_point = np.array([nose.x, nose.y, nose.z])
            else:
                left_sh = results.pose_landmarks.landmark[11]
                right_sh = results.pose_landmarks.landmark[12]
                reference_point = np.array([(left_sh.x+right_sh.x)/2, (left_sh.y+right_sh.y)/2, (left_sh.z+right_sh.z)/2])

        lh = self.extract_hand_features(results.left_hand_landmarks, reference_point)
        rh = self.extract_hand_features(results.right_hand_landmarks, reference_point)
        aux = self.extract_body_features(results.pose_landmarks, reference_point)

        if not (np.all(lh == 0) and np.all(rh == 0) and np.all(aux == 0)):
            return np.concatenate([lh, rh, aux])
        return None

    def process_results(self, results):
        """
        Processes MediaPipe results and returns a list of candidates if a stable sign is detected.
        Otherwise returns None.
        """
        feat = self.extract_features_from_results(results)
        if feat is not None:
            probs = self.model.predict(feat.reshape(1, -1), verbose=0)[0]
            
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
            current_label = self.classes[top_idx]
            
            self.window.append(current_label)
            
            if len(self.window) == 8:
                # Layer 1: Window Majority
                majority_label = max(set(self.window), key=list(self.window).count)
                
                # Layer 2: Consecutive Majority Stability
                if majority_label == self.prev_majority:
                    self.stability_counter += 1
                else:
                    self.prev_majority = majority_label
                    self.stability_counter = 1
                
                if self.stability_counter >= 8:
                    # Translate to human-readable label
                    human_label = LABEL_MAP.get(majority_label, str(majority_label))
                    
                    # Only commit if it's a new word
                    if human_label != self.last_committed_word:
                        top_6_indices = np.argsort(self.prev_probs)[-6:][::-1]
                        candidates = []
                        for idx in top_6_indices:
                            raw_label = self.classes[idx]
                            label = LABEL_MAP.get(raw_label, str(raw_label))
                            candidates.append({
                                "label": label,
                                "accuracy": float(self.prev_probs[idx])
                            })
                        
                        self.last_committed_word = human_label
                        self.stability_counter = 0 # Reset Layer 2
                        print(f"  [DEBUG] MLP Committed: {human_label} (Conf: {conf:.2f})")
                        print(f"  [DEBUG] Top 3: {[(LABEL_MAP.get(self.classes[i], self.classes[i]), f'{self.prev_probs[i]:.2f}') for i in top_6_indices[:3]]}")
                        # Debug specific classes
                        try:
                            # Find indices for relevant classes using string string matching if needed, or hardcoded knowledge
                            # Classes are numeric strings like '19', '0'.
                            idx_me = np.where(self.classes == '19')[0]
                            idx_i = np.where(self.classes == '11')[0]
                            idx_a = np.where(self.classes == '0')[0]
                            
                            debug_probs = []
                            if len(idx_me) > 0: debug_probs.append(f"Me(19): {self.prev_probs[idx_me[0]]:.2f}")
                            if len(idx_i) > 0: debug_probs.append(f"I(11): {self.prev_probs[idx_i[0]]:.2f}")
                            if len(idx_a) > 0: debug_probs.append(f"A(0): {self.prev_probs[idx_a[0]]:.2f}")
                            print(f"  [DEBUG] Specifics: {', '.join(debug_probs)}")
                        except Exception as e:
                            print(f"Debug print error: {e}")

                        return candidates
                    
                    self.stability_counter = 0 # Reset Layer 2
        return None

    def predict_video(self, video_path):
        """Processes a video and returns a list of stable detections (Top 6 each) using double-layer stability."""
        cap = cv2.VideoCapture(video_path)
        stable_detections = []
        
        self.reset_inference()

        print(f"\n[DEBUG] MLP Processing video (EMA + Double Stability): {os.path.basename(video_path)}")
        
        import time
        start_time = time.time()
        
        while cap.isOpened():
            # Prevent infinite hang in case of corrupt webm loop
            if time.time() - start_time > 30:
                print("[DEBUG] MLP Processing timed out after 30 seconds.")
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
    #  INFERENCE LOOP
    # =========================================================================

    def run(self):
        cap = cv2.VideoCapture(0)
        
        print("\n--- Starting Webcam Inference (Press 'q' to quit) ---")
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # Flip for mirror view
            frame = cv2.flip(frame, 1)
            
            # --- Data Processing ---
            input_vector = self.extract_single_frame(frame)

            # 3. Predict (Only if at least one hand or significant body movement is detected)
            if input_vector is not None:
                # Reshape for Model (Batch=1, Features=188)
                input_tensor = input_vector.reshape(1, -1)
                
                prediction = self.model.predict(input_tensor, verbose=0)
                class_idx = np.argmax(prediction)
                confidence = np.max(prediction)
                
                raw_label = self.classes[class_idx]
                label_text = LABEL_MAP.get(raw_label, str(raw_label))

                # --- UI: Display Prediction ---
                if confidence > self.threshold:
                    # Green Text for High Confidence
                    color = (0, 255, 0)
                    display_text = f"{label_text} ({confidence*100:.1f}%)"
                else:
                    # Yellow Text for Low Confidence
                    color = (0, 255, 255)
                    display_text = f"Unsure... ({confidence*100:.1f}%)"

                # Draw Background Box for text
                cv2.rectangle(frame, (10, 30), (400, 80), (0, 0, 0), -1)
                cv2.putText(frame, display_text, (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            else:
                # No hands detected state
                cv2.putText(frame, "Waiting for hands...", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)

            cv2.imshow('Sign Language Recognition', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
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
    base_dir = 'models/face_remove_model'
    if os.path.exists(base_dir):
        subdirs = [os.path.join(base_dir, d) for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
        if subdirs:
            latest_model_dir = max(subdirs, key=os.path.getmtime)
            load_labels_from_data()
            return SignLanguageInference(model_dir=latest_model_dir)
    return None

if __name__ == '__main__':
    load_labels_from_data()
    app = get_inference_model()
    if app:
        app.run()
    else:
        print("No model found.")
