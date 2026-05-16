"""
Body-aware preprocessing for dynamic sign-language recognition.

Key upgrades in this version:
- Hands are encoded relative to shoulders and elbows
- Shoulder-centered normalization makes signs location-aware on the body
- Hand-shape normalization reduces sensitivity to hand size
- Motion-focused trimming helps when the sign occurs anywhere in the clip
- Speed-normalized temporal deltas reduce dependence on signer speed
"""

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '2'
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import numpy as np
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from sklearn.model_selection import train_test_split

from utils import extract_frames, extract_hand_pose_landmarks

# ---------------- PATHS ----------------
BASE_DIR = Path(__file__).resolve().parent
DATASET_ROOT = BASE_DIR / "dataset"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = BASE_DIR / "result_models" / f"processed_add_feature_{TIMESTAMP}"

# ---------------- CONFIG ----------------
TARGET_FRAMES = 60
MAX_SOURCE_FRAMES = 120
TRAIN_AUGMENT_COPIES = 2

HAND_DIM = 126
POSE_DIM = 12
FACE_DIM = 9
RAW_DIM = HAND_DIM + POSE_DIM + FACE_DIM

STATIC_FEATURE_DIM = 324
FEATURE_DIM = STATIC_FEATURE_DIM * 2


def build_label_map(dataset_root: Path) -> dict:
    classes = sorted([d.name for d in dataset_root.iterdir() if d.is_dir()])
    label_map = {cls: idx for idx, cls in enumerate(classes)}
    np.save(OUTPUT_DIR / "label_map.npy", label_map)
    return label_map


def resample_sequence(sequence: np.ndarray, target_len: int = TARGET_FRAMES) -> np.ndarray:
    """Linearly resample a sequence to a fixed number of frames."""
    sequence = np.asarray(sequence, dtype=np.float32)
    time_steps = len(sequence)

    if time_steps == 0:
        return np.zeros((target_len, sequence.shape[1]), dtype=np.float32)
    if time_steps == 1:
        return np.repeat(sequence, target_len, axis=0).astype(np.float32)
    if time_steps == target_len:
        return sequence.astype(np.float32)

    positions = np.linspace(0, time_steps - 1, target_len)
    left = np.floor(positions).astype(int)
    right = np.ceil(positions).astype(int)
    alpha = (positions - left).reshape(-1, 1)
    resampled = (1.0 - alpha) * sequence[left] + alpha * sequence[right]
    return resampled.astype(np.float32)


def trim_empty_frames(sequence: np.ndarray) -> np.ndarray:
    """Remove leading and trailing frames with no detected landmarks."""
    valid = np.any(sequence != 0, axis=1)
    if not np.any(valid):
        return sequence[:1].copy()

    start = int(np.argmax(valid))
    end = len(valid) - int(np.argmax(valid[::-1]))
    return sequence[start:end].copy()


def _hand_scale(hand_points: np.ndarray) -> float:
    if not np.any(hand_points):
        return 0.0

    wrist = hand_points[0]
    candidates = [5, 9, 13, 17]
    distances = [np.linalg.norm(hand_points[idx] - wrist) for idx in candidates]
    scale = max(distances)
    return float(scale)


def estimate_body_reference(sequence: np.ndarray) -> tuple[np.ndarray, float]:
    """Estimate a stable body center and scale for one video."""
    centers = []
    scales = []

    for frame in sequence:
        hands = frame[:HAND_DIM].reshape(2, 21, 3)
        pose = frame[HAND_DIM:HAND_DIM + POSE_DIM].reshape(4, 3)
        face = frame[HAND_DIM + POSE_DIM:RAW_DIM].reshape(3, 3)
        left_shoulder, right_shoulder, left_elbow, right_elbow = pose
        nose, left_eyebrow, right_eyebrow = face

        if np.any(left_shoulder) and np.any(right_shoulder):
            centers.append((left_shoulder + right_shoulder) / 2.0)
            scales.append(np.linalg.norm(left_shoulder - right_shoulder))

        for shoulder, elbow in ((left_shoulder, left_elbow), (right_shoulder, right_elbow)):
            if np.any(shoulder) and np.any(elbow):
                centers.append(shoulder)
                scales.append(2.0 * np.linalg.norm(shoulder - elbow))

        for hand_points in hands:
            hand_size = _hand_scale(hand_points)
            if hand_size > 0:
                centers.append(hand_points[0])
                scales.append(4.0 * hand_size)

        if np.any(nose):
            centers.append(nose)
        if np.any(left_eyebrow) and np.any(right_eyebrow):
            centers.append((left_eyebrow + right_eyebrow) / 2.0)
            scales.append(2.0 * np.linalg.norm(left_eyebrow - right_eyebrow))

    if not centers:
        return np.zeros(3, dtype=np.float32), 1.0

    center = np.median(np.stack(centers, axis=0), axis=0).astype(np.float32)
    scale = float(np.median(np.asarray(scales, dtype=np.float32)))
    if scale < 1e-4:
        scale = 1.0

    return center, scale


def normalize_landmarks(sequence: np.ndarray) -> np.ndarray:
    """Normalize all coordinates relative to the signer body."""
    sequence = np.asarray(sequence, dtype=np.float32).copy()
    center, scale = estimate_body_reference(sequence)

    for frame_idx in range(sequence.shape[0]):
        frame = sequence[frame_idx]
        hands = frame[:HAND_DIM].reshape(2, 21, 3)
        pose = frame[HAND_DIM:HAND_DIM + POSE_DIM].reshape(4, 3)
        face = frame[HAND_DIM + POSE_DIM:RAW_DIM].reshape(3, 3)

        for hand_idx in range(2):
            if np.any(hands[hand_idx]):
                hands[hand_idx] = (hands[hand_idx] - center) / scale

        for pose_idx in range(4):
            if np.any(pose[pose_idx]):
                pose[pose_idx] = (pose[pose_idx] - center) / scale

        for face_idx in range(3):
            if np.any(face[face_idx]):
                face[face_idx] = (face[face_idx] - center) / scale

        frame[:HAND_DIM] = hands.reshape(-1)
        frame[HAND_DIM:HAND_DIM + POSE_DIM] = pose.reshape(-1)
        frame[HAND_DIM + POSE_DIM:RAW_DIM] = face.reshape(-1)

    return sequence


def extract_hand_shape_features(body_relative_sequence: np.ndarray) -> np.ndarray:
    """Encode hand posture independent of signer hand size."""
    hands = body_relative_sequence[:, :HAND_DIM].reshape(-1, 2, 21, 3)
    shape_features = np.zeros_like(hands, dtype=np.float32)

    for frame_idx in range(hands.shape[0]):
        for hand_idx in range(2):
            hand_points = hands[frame_idx, hand_idx]
            if not np.any(hand_points):
                continue

            wrist = hand_points[0]
            scale = _hand_scale(hand_points)
            if scale < 1e-4:
                scale = 1.0

            shape_features[frame_idx, hand_idx] = (hand_points - wrist) / scale

    return shape_features.reshape(-1, HAND_DIM).astype(np.float32)


def extract_pose_relative_features(body_relative_sequence: np.ndarray) -> np.ndarray:
    return body_relative_sequence[:, HAND_DIM:RAW_DIM].astype(np.float32)


def extract_relation_features(body_relative_sequence: np.ndarray) -> np.ndarray:
    """Hand positions relative to shoulders, elbows, nose, and eyebrows."""
    hands = body_relative_sequence[:, :HAND_DIM].reshape(-1, 2, 21, 3)
    pose = body_relative_sequence[:, HAND_DIM:HAND_DIM + POSE_DIM].reshape(-1, 4, 3)
    face = body_relative_sequence[:, HAND_DIM + POSE_DIM:RAW_DIM].reshape(-1, 3, 3)
    relation_features = np.zeros((body_relative_sequence.shape[0], 42), dtype=np.float32)

    for frame_idx in range(body_relative_sequence.shape[0]):
        left_shoulder, right_shoulder, left_elbow, right_elbow = pose[frame_idx]
        nose, left_eyebrow, right_eyebrow = face[frame_idx]
        references = ((left_shoulder, left_elbow), (right_shoulder, right_elbow))
        face_references = (nose, left_eyebrow, right_eyebrow)

        cursor = 0
        for hand_idx in range(2):
            hand_points = hands[frame_idx, hand_idx]
            shoulder, elbow = references[hand_idx]

            if np.any(hand_points):
                wrist = hand_points[0]
                center = hand_points.mean(axis=0)
            else:
                wrist = np.zeros(3, dtype=np.float32)
                center = np.zeros(3, dtype=np.float32)

            relation_features[frame_idx, cursor:cursor + 3] = center - shoulder if np.any(hand_points) and np.any(shoulder) else 0.0
            cursor += 3
            relation_features[frame_idx, cursor:cursor + 3] = center - elbow if np.any(hand_points) and np.any(elbow) else 0.0
            cursor += 3
            relation_features[frame_idx, cursor:cursor + 3] = wrist - shoulder if np.any(hand_points) and np.any(shoulder) else 0.0
            cursor += 3
            relation_features[frame_idx, cursor:cursor + 3] = wrist - elbow if np.any(hand_points) and np.any(elbow) else 0.0
            cursor += 3

            for face_ref in face_references:
                relation_features[frame_idx, cursor:cursor + 3] = center - face_ref if np.any(hand_points) and np.any(face_ref) else 0.0
                cursor += 3

    return relation_features


def extract_presence_features(sequence: np.ndarray) -> np.ndarray:
    """Binary flags indicating which body parts were detected."""
    hands = sequence[:, :HAND_DIM].reshape(-1, 2, 21, 3)
    pose = sequence[:, HAND_DIM:HAND_DIM + POSE_DIM].reshape(-1, 4, 3)
    face = sequence[:, HAND_DIM + POSE_DIM:RAW_DIM].reshape(-1, 3, 3)

    features = np.zeros((sequence.shape[0], 9), dtype=np.float32)
    features[:, 0] = np.any(hands[:, 0] != 0, axis=(1, 2))
    features[:, 1] = np.any(hands[:, 1] != 0, axis=(1, 2))
    features[:, 2] = np.any(pose[:, 0] != 0, axis=1)
    features[:, 3] = np.any(pose[:, 1] != 0, axis=1)
    features[:, 4] = np.any(pose[:, 2] != 0, axis=1)
    features[:, 5] = np.any(pose[:, 3] != 0, axis=1)
    features[:, 6] = np.any(face[:, 0] != 0, axis=1)
    features[:, 7] = np.any(face[:, 1] != 0, axis=1)
    features[:, 8] = np.any(face[:, 2] != 0, axis=1)
    return features


def add_speed_invariant_deltas(features: np.ndarray) -> np.ndarray:
    """Add temporal change features while reducing sensitivity to signing speed."""
    deltas = np.diff(features, axis=0, prepend=features[:1]).astype(np.float32)
    motion_scale = np.mean(np.linalg.norm(deltas, axis=1))
    if motion_scale < 1e-4:
        motion_scale = 1.0
    return deltas / motion_scale


def add_coordinate_noise(features: np.ndarray, std: float = 0.01) -> np.ndarray:
    noise = np.random.normal(0.0, std, features.shape).astype(np.float32)
    return features + noise


def focus_active_segment(sequence: np.ndarray) -> np.ndarray:
    """Crop around the part of the clip where the sign is actually happening."""
    sequence = trim_empty_frames(sequence)
    if len(sequence) <= TARGET_FRAMES:
        return sequence

    normalized = normalize_landmarks(sequence)
    hands = normalized[:, :HAND_DIM]
    body_context = normalized[:, HAND_DIM:RAW_DIM]

    hand_motion = np.mean(np.abs(np.diff(hands, axis=0)), axis=1)
    body_motion = np.mean(np.abs(np.diff(body_context, axis=0)), axis=1)
    motion = hand_motion + 0.5 * body_motion

    if len(motion) == 0 or np.all(motion < 1e-6):
        return sequence

    kernel = np.array([1, 2, 3, 2, 1], dtype=np.float32)
    kernel /= kernel.sum()
    smoothed = np.convolve(motion, kernel, mode="same")

    threshold = max(float(np.percentile(smoothed, 60)), float(smoothed.mean()))
    active_idx = np.where(smoothed >= threshold)[0]
    if len(active_idx) == 0:
        return sequence

    start = max(0, int(active_idx[0]) - 6)
    end = min(len(sequence), int(active_idx[-1]) + 7)

    if end - start < 12:
        peak = int(np.argmax(smoothed))
        start = max(0, peak - 6)
        end = min(len(sequence), peak + 7)

    return sequence[start:end]


def temporal_crop(sequence: np.ndarray, crop_ratio: float = 0.1) -> np.ndarray:
    """Randomly crop temporal margins while keeping the active sign."""
    if len(sequence) <= 8:
        return sequence

    max_crop = max(1, int(len(sequence) * crop_ratio))
    start_crop = np.random.randint(0, max_crop + 1)
    end_crop = np.random.randint(0, max_crop + 1)

    start = min(start_crop, len(sequence) - 4)
    end = max(start + 4, len(sequence) - end_crop)
    return sequence[start:end]


def build_feature_sequence(raw_sequence: np.ndarray, augment: bool = False) -> np.ndarray:
    body_relative = normalize_landmarks(raw_sequence)
    hand_shape = extract_hand_shape_features(body_relative)
    pose_relative = extract_pose_relative_features(body_relative)
    relation = extract_relation_features(body_relative)
    presence = extract_presence_features(raw_sequence)

    static_features = np.concatenate(
        [
            body_relative[:, :HAND_DIM],
            hand_shape,
            pose_relative,
            relation,
            presence,
        ],
        axis=1,
    ).astype(np.float32)

    if augment:
        static_features[:, :-9] = add_coordinate_noise(static_features[:, :-9], std=0.008)

    dynamic_features = add_speed_invariant_deltas(static_features)
    return np.concatenate([static_features, dynamic_features], axis=1).astype(np.float32)


def preprocess_video_frames(frames, augment: bool = False) -> np.ndarray | None:
    raw_sequence = extract_hand_pose_landmarks(frames)
    raw_sequence = trim_empty_frames(raw_sequence)

    if len(raw_sequence) < 5:
        return None

    raw_sequence = focus_active_segment(raw_sequence)
    if augment:
        raw_sequence = temporal_crop(raw_sequence, crop_ratio=0.12)

    raw_sequence = resample_sequence(raw_sequence, TARGET_FRAMES)
    features = build_feature_sequence(raw_sequence, augment=augment)

    if features.shape != (TARGET_FRAMES, FEATURE_DIM):
        return None

    return features.astype(np.float32)


import concurrent.futures
import multiprocessing


def _init_worker():
    global _worker_models
    import mediapipe as mp
    mp_hands = mp.solutions.hands
    mp_pose = mp.solutions.pose
    mp_face_mesh = mp.solutions.face_mesh
    
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    face = mp_face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    _worker_models = (hands, pose, face)

def _worker_process_video(video_data):
    video_path, label = video_data
    global _worker_models
    try:
        from utils import extract_hand_pose_landmarks_from_video
        # Process EVERY frame for maximum landmark tracking accuracy
        raw_sequence = extract_hand_pose_landmarks_from_video(str(video_path), models=_worker_models)
        raw_sequence = trim_empty_frames(raw_sequence)

        if len(raw_sequence) < 5:
            return None
        
        return (focus_active_segment(raw_sequence), label)
    except Exception as exc:
        print(f"[WARN] Skipping {video_path}: {exc}")
        return None


def get_preprocess_worker_count() -> int:
    """Limit MediaPipe worker processes to avoid exhausting CPU/RAM."""
    cpu_count = multiprocessing.cpu_count()
    env_value = os.environ.get("PREPROCESS_WORKERS")
    if env_value:
        try:
            requested = int(env_value)
            if requested > 0:
                return min(requested, cpu_count)
        except ValueError:
            print(f"[WARN] Ignoring invalid PREPROCESS_WORKERS={env_value!r}")

    return max(1, min(cpu_count - 1, 4))


def preprocess_video_file(video_path: str | Path, augment: bool = False) -> np.ndarray | None:
    """Build inference features from a video using the same full-frame path as training."""
    from utils import extract_hand_pose_landmarks_from_video

    raw_sequence = extract_hand_pose_landmarks_from_video(str(video_path))
    raw_sequence = trim_empty_frames(raw_sequence)

    if len(raw_sequence) < 5:
        return None

    raw_sequence = focus_active_segment(raw_sequence)
    if augment:
        raw_sequence = temporal_crop(raw_sequence, crop_ratio=0.12)

    raw_sequence = resample_sequence(raw_sequence, TARGET_FRAMES)
    features = build_feature_sequence(raw_sequence, augment=augment)

    if features.shape != (TARGET_FRAMES, FEATURE_DIM):
        return None

    return features.astype(np.float32)


def process_dataset(dataset_root: Path):
    """Load raw videos in parallel and build train/validation tensors."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    label_map = build_label_map(dataset_root)
    
    tasks = []
    for class_dir in sorted(dataset_root.iterdir()):
        if not class_dir.is_dir():
            continue
        label = label_map[class_dir.name]
        for ext in ("*.mp4", "*.avi", "*.mov", "*.mkv", "*.webm"):
            for video_path in sorted(class_dir.glob(ext)):
                tasks.append((video_path, label))

    if not tasks:
        raise RuntimeError("No videos found in dataset root.")

    worker_count = get_preprocess_worker_count()
    print(f"Found {len(tasks)} videos. Processing in parallel using {worker_count} workers...")
    
    raw_samples = []
    labels = []
    
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=worker_count,
        initializer=_init_worker
    ) as executor:
        # Using as_completed with tqdm for real-time progress updates
        future_to_video = {executor.submit(_worker_process_video, task): task for task in tasks}
        
        for future in tqdm(concurrent.futures.as_completed(future_to_video), total=len(tasks), desc="Extracting Landmarks"):
            res = future.result()
            if res is not None:
                sample, label = res
                raw_samples.append(sample)
                labels.append(label)
        
    if not raw_samples:
        raise RuntimeError("No valid samples were extracted from the dataset.")


    labels = np.array(labels, dtype=np.int64)
    indices = np.arange(len(raw_samples))

    try:
        train_idx, val_idx = train_test_split(
            indices,
            test_size=0.2,
            random_state=42,
            stratify=labels,
        )
    except ValueError:
        print("[WARN] Stratify failed. Splitting without stratification.")
        train_idx, val_idx = train_test_split(
            indices,
            test_size=0.2,
            random_state=42,
        )

    print("Building feature sequences...")
    X_train, y_train = [], []
    for idx in train_idx:
        base_sequence = raw_samples[idx]
        X_train.append(build_feature_sequence(resample_sequence(base_sequence), augment=False))
        y_train.append(labels[idx])

        for _ in range(TRAIN_AUGMENT_COPIES - 1):
            augmented_sequence = temporal_crop(base_sequence, crop_ratio=0.12)
            augmented_sequence = resample_sequence(augmented_sequence)
            X_train.append(build_feature_sequence(augmented_sequence, augment=True))
            y_train.append(labels[idx])

    X_val, y_val = [], []
    for idx in val_idx:
        val_sequence = resample_sequence(raw_samples[idx])
        X_val.append(build_feature_sequence(val_sequence, augment=False))
        y_val.append(labels[idx])

    X_train = np.stack(X_train).astype(np.float32)
    y_train = np.array(y_train, dtype=np.int64)
    X_val = np.stack(X_val).astype(np.float32)
    y_val = np.array(y_val, dtype=np.int64)

    X_all = np.concatenate([X_train, X_val], axis=0)
    y_all = np.concatenate([y_train, y_val], axis=0)

    np.save(OUTPUT_DIR / "X.npy", X_all)
    np.save(OUTPUT_DIR / "y.npy", y_all)
    np.save(OUTPUT_DIR / "X_train.npy", X_train)
    np.save(OUTPUT_DIR / "y_train.npy", y_train)
    np.save(OUTPUT_DIR / "X_val.npy", X_val)
    np.save(OUTPUT_DIR / "y_val.npy", y_val)

    print(f"Processed train samples: {len(X_train)}, shape: {X_train.shape}")
    print(f"Processed val samples:   {len(X_val)}, shape: {X_val.shape}")

    return X_train, y_train, X_val, y_val, label_map



if __name__ == "__main__":
    process_dataset(DATASET_ROOT)
    print("Train/validation features saved.")
