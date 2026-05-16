import cv2
import numpy as np
import mediapipe as mp
import threading
from typing import List

# Initialize MediaPipe modules once for reuse
mp_hands = mp.solutions.hands
mp_pose = mp.solutions.pose
mp_face_mesh = mp.solutions.face_mesh

POSE_KEYPOINTS = [
    mp_pose.PoseLandmark.LEFT_SHOULDER,
    mp_pose.PoseLandmark.RIGHT_SHOULDER,
    mp_pose.PoseLandmark.LEFT_ELBOW,
    mp_pose.PoseLandmark.RIGHT_ELBOW,
]


def _connection_indices(connections) -> list[int]:
    indices = set()
    for start, end in connections:
        indices.add(int(start))
        indices.add(int(end))
    return sorted(indices)


LEFT_EYEBROW_INDICES = _connection_indices(mp.solutions.face_mesh_connections.FACEMESH_LEFT_EYEBROW)
RIGHT_EYEBROW_INDICES = _connection_indices(mp.solutions.face_mesh_connections.FACEMESH_RIGHT_EYEBROW)
NOSE_TIP_INDEX = 1

_DEFAULT_MODELS = None
_DEFAULT_MODELS_LOCK = threading.Lock()


def _create_default_models():
    print("[MediaPipe] Creating reusable Hands/Pose/FaceMesh models")
    return (
        mp_hands.Hands(static_image_mode=False, max_num_hands=2),
        mp_pose.Pose(static_image_mode=False, model_complexity=0),
        mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1),
    )


def get_default_mediapipe_models():
    global _DEFAULT_MODELS
    with _DEFAULT_MODELS_LOCK:
        if _DEFAULT_MODELS is None:
            _DEFAULT_MODELS = _create_default_models()
        return _DEFAULT_MODELS


def extract_frames(video_path: str, max_frames: int = 30) -> List[np.ndarray]:
    """Extract up to ``max_frames`` frames from ``video_path``.
    
    REVERTED: Now reads sequentially to ensure no frames are skipped if needed, 
    but still returns a sampled subset to avoid memory overflow.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Unable to open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        frames_list = []
        while len(frames_list) < max_frames:
            ret, frame = cap.read()
            if not ret: break
            frames_list.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        cap.release()
        if not frames_list:
            raise ValueError(f"Video {video_path} contains no frames")
        return frames_list

    indices = np.linspace(0, total_frames - 1, max_frames, dtype=int)
    selected = set(indices)
    frames = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx in selected:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        frame_idx += 1

    cap.release()
    return frames


def extract_hand_pose_landmarks_from_video(video_path: str, models=None) -> np.ndarray:
    """Read every single frame of the video and extract landmarks.
    
    This is the most accurate way as it allows MediaPipe to track landmarks 
    across every frame without skipping, which is critical for tracking state.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Unable to open video: {video_path}")

    if models is None:
        models = get_default_mediapipe_models()

    hands, pose, face_mesh = models
    with _DEFAULT_MODELS_LOCK:
        return _process_video_stream(cap, hands, pose, face_mesh)


def _process_video_stream(cap, hands, pose, face_mesh):
    landmarks = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Mirror effect to match dataset collection
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_data = np.zeros(147, dtype=np.float32)

        # 1. Hands
        hand_result = hands.process(rgb_frame)
        if hand_result.multi_hand_landmarks and hand_result.multi_handedness:
            for idx, hand in enumerate(hand_result.multi_hand_landmarks):
                label = hand_result.multi_handedness[idx].classification[0].label
                coords = np.array([(lm.x, lm.y, lm.z) for lm in hand.landmark], dtype=np.float32).reshape(-1)
                if label == "Right":
                    frame_data[63:126] = coords
                else:
                    frame_data[:63] = coords

        # 2. Pose
        pose_result = pose.process(rgb_frame)
        if pose_result.pose_landmarks:
            pose_values = []
            for keypoint in POSE_KEYPOINTS:
                landmark = pose_result.pose_landmarks.landmark[keypoint]
                pose_values.extend([landmark.x, landmark.y, landmark.z])
            frame_data[126:138] = np.array(pose_values, dtype=np.float32)

        # 3. Face
        face_result = face_mesh.process(rgb_frame)
        if face_result.multi_face_landmarks:
            face_landmarks = face_result.multi_face_landmarks[0].landmark
            nose = face_landmarks[NOSE_TIP_INDEX]
            left_eyebrow = np.array([[face_landmarks[idx].x, face_landmarks[idx].y, face_landmarks[idx].z] for idx in LEFT_EYEBROW_INDICES], dtype=np.float32).mean(axis=0)
            right_eyebrow = np.array([[face_landmarks[idx].x, face_landmarks[idx].y, face_landmarks[idx].z] for idx in RIGHT_EYEBROW_INDICES], dtype=np.float32).mean(axis=0)
            
            frame_data[138:] = [
                nose.x, nose.y, nose.z,
                left_eyebrow[0], left_eyebrow[1], left_eyebrow[2],
                right_eyebrow[0], right_eyebrow[1], right_eyebrow[2]
            ]

        landmarks.append(frame_data)
    
    cap.release()
    if not landmarks:
        return np.zeros((1, 147), dtype=np.float32)
    return np.stack(landmarks, axis=0)


def extract_hand_pose_landmarks(frames: List[np.ndarray], models=None) -> np.ndarray:
    """Kept for backward compatibility with pre-sampled frame lists."""
    if models is None:
        with mp_hands.Hands(static_image_mode=False, max_num_hands=2) as hands, \
             mp_pose.Pose(static_image_mode=False, model_complexity=0) as pose, \
             mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1) as face_mesh:
            return _process_frame_list(frames, hands, pose, face_mesh)
    else:
        hands, pose, face_mesh = models
        return _process_frame_list(frames, hands, pose, face_mesh)


def _process_frame_list(frames, hands, pose, face_mesh):
    results = []
    for frame in frames:
        frame_data = np.zeros(147, dtype=np.float32)
        # (Same processing logic as _process_video_stream but for a single frame)
        # We'll just call a helper
        results.append(_process_single_frame(frame, hands, pose, face_mesh))
    return np.stack(results, axis=0)

def _process_single_frame(frame, hands, pose, face_mesh):
    frame_data = np.zeros(147, dtype=np.float32)
    hand_result = hands.process(frame)
    if hand_result.multi_hand_landmarks and hand_result.multi_handedness:
        for idx, hand in enumerate(hand_result.multi_hand_landmarks):
            label = hand_result.multi_handedness[idx].classification[0].label
            coords = np.array([(lm.x, lm.y, lm.z) for lm in hand.landmark], dtype=np.float32).reshape(-1)
            if label == "Right": frame_data[63:126] = coords
            else: frame_data[:63] = coords
    pose_result = pose.process(frame)
    if pose_result.pose_landmarks:
        pose_values = []
        for keypoint in POSE_KEYPOINTS:
            landmark = pose_result.pose_landmarks.landmark[keypoint]
            pose_values.extend([landmark.x, landmark.y, landmark.z])
        frame_data[126:138] = np.array(pose_values, dtype=np.float32)
    face_result = face_mesh.process(frame)
    if face_result.multi_face_landmarks:
        face_landmarks = face_result.multi_face_landmarks[0].landmark
        nose = face_landmarks[NOSE_TIP_INDEX]
        left_eb = np.array([[face_landmarks[idx].x, face_landmarks[idx].y, face_landmarks[idx].z] for idx in LEFT_EYEBROW_INDICES], dtype=np.float32).mean(axis=0)
        right_eb = np.array([[face_landmarks[idx].x, face_landmarks[idx].y, face_landmarks[idx].z] for idx in RIGHT_EYEBROW_INDICES], dtype=np.float32).mean(axis=0)
        frame_data[138:] = [nose.x, nose.y, nose.z, left_eb[0], left_eb[1], left_eb[2], right_eb[0], right_eb[1], right_eb[2]]
    return frame_data

def pad_sequence(seq: np.ndarray, target_len: int = 30) -> np.ndarray:
    """Pad or uniformly truncate a sequence to ``target_len`` frames."""
    time_steps = seq.shape[0]
    if time_steps == target_len: return seq
    if time_steps > target_len:
        indices = np.linspace(0, time_steps - 1, target_len, dtype=int)
        return seq[indices]
    pad = np.zeros((target_len - time_steps, seq.shape[1]), dtype=seq.dtype)
    return np.concatenate([seq, pad], axis=0)
