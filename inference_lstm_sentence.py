"""
LSTM-based sentence inference for sign-language videos.
Adapted for use in the Sign Language App.
"""

import os
import sys
import cv2
import time
import numpy as np
import torch
from typing import List, Dict

from data_preprocessing_add_features import (
    FEATURE_DIM,
    TARGET_FRAMES,
    build_feature_sequence,
    focus_active_segment,
    resample_sequence,
    trim_empty_frames,
)
from model_add_feature import SignLanguageLSTM
from utils import extract_hand_pose_landmarks_from_video

# --- CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "lstm_sentence", "model_best.pt")

WINDOW_SIZE = 45
WINDOW_STRIDE = 1
PREDICTION_CONFIDENCE_THRESHOLD = 0.60
MERGE_GAP_FRAMES = 12
CUT_THRESHOLD_PERCENTILE = 98.5
MIN_CUT_GAP_FRAMES = 20
MIN_SEGMENT_FRAMES = 20

class LSTMRecognizer:
    def __init__(self, model_path=MODEL_PATH):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model, self.idx_to_label = self.load_model(model_path)
        self.last_frame_count = 0
        self.model.to(self.device)
        self.model.eval()
        print(f"[LSTMRecognizer] Model loaded on {self.device}")

    def load_model(self, model_path):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found at {model_path}")

        checkpoint = torch.load(model_path, map_location="cpu")
        label_map = checkpoint["label_map"]
        idx_to_label = {int(v): k for k, v in label_map.items()}
        input_size = checkpoint.get("input_size", FEATURE_DIM)

        model = SignLanguageLSTM(input_size=input_size, num_classes=len(label_map))
        model.load_state_dict(checkpoint["model_state_dict"])
        return model, idx_to_label

    def load_video_frames(self, video_path: str):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Unable to open video: {video_path}")

        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        cap.release()
        return frames

    def compute_frame_diff_scores(self, frames: List[np.ndarray]):
        if len(frames) < 2:
            return np.zeros(len(frames), dtype=np.float32)

        diffs = [0.0]
        for idx in range(1, len(frames)):
            prev_gray = cv2.cvtColor(frames[idx - 1], cv2.COLOR_RGB2GRAY)
            curr_gray = cv2.cvtColor(frames[idx], cv2.COLOR_RGB2GRAY)
            diffs.append(float(np.mean(np.abs(curr_gray.astype(np.float32) - prev_gray.astype(np.float32)))))
        return np.asarray(diffs, dtype=np.float32)

    def find_cut_points(self, frames: List[np.ndarray]):
        scores = self.compute_frame_diff_scores(frames)
        if len(scores) < 2:
            return []

        non_zero = scores[scores > 1e-5]
        if len(non_zero) == 0:
            return []

        threshold = float(np.percentile(non_zero, CUT_THRESHOLD_PERCENTILE))
        peaks = [idx for idx, value in enumerate(scores) if value >= threshold]

        filtered = []
        for idx in peaks:
            if not filtered or idx - filtered[-1] >= MIN_CUT_GAP_FRAMES:
                filtered.append(idx)
            elif scores[idx] > scores[filtered[-1]]:
                filtered[-1] = idx
        return filtered

    def build_cut_regions(self, total_frames: int, cut_points: List[int]):
        boundaries = [0] + [point for point in cut_points if 0 < point < total_frames] + [total_frames]
        regions = []
        for start, end in zip(boundaries[:-1], boundaries[1:]):
            if end - start >= MIN_SEGMENT_FRAMES:
                regions.append((start, end))
        return regions

    def make_window_predictions(self, raw_sequence: np.ndarray, region_start: int, region_end: int):
        region = raw_sequence[region_start:region_end]
        region = trim_empty_frames(region)

        if len(region) < 5:
            return []

        windows = []
        if len(region) <= WINDOW_SIZE:
            windows.append((0, len(region)))
        else:
            for start in range(0, len(region) - WINDOW_SIZE + 1, WINDOW_STRIDE):
                windows.append((start, start + WINDOW_SIZE))
            last_start = len(region) - WINDOW_SIZE
            if not windows or windows[-1][0] != last_start:
                windows.append((last_start, len(region)))

        predictions = []
        for local_start, local_end in windows:
            window_sequence = region[local_start:local_end]
            window_sequence = trim_empty_frames(window_sequence)
            if len(window_sequence) < 5:
                continue

            feature_variants = self.build_window_feature_variants(window_sequence)
            if not feature_variants:
                continue

            with torch.no_grad():
                logits_list = []
                for features in feature_variants:
                    x = torch.from_numpy(features).unsqueeze(0).float().to(self.device)
                    logits_list.append(self.model(x))
                logits = torch.stack(logits_list, dim=0).mean(dim=0)
                probs = torch.softmax(logits, dim=1)

            conf, pred_idx = torch.max(probs, dim=1)
            confidence = float(conf.item())
            label = self.idx_to_label[int(pred_idx.item())]

            predictions.append({
                "label": label,
                "confidence": confidence,
                "start": region_start + local_start,
                "end": region_start + local_end,
            })
        return predictions

    def build_window_feature_variants(self, window_sequence: np.ndarray):
        base_sequence = focus_active_segment(window_sequence)
        variants = [base_sequence]

        if len(base_sequence) > 12:
            variants.extend(
                [
                    base_sequence[2:],
                    base_sequence[:-2],
                    base_sequence[1:-1],
                ]
            )

        features = []
        seen = set()
        for variant in variants:
            variant = trim_empty_frames(variant)
            if len(variant) < 5:
                continue

            variant = resample_sequence(variant, TARGET_FRAMES)
            key = variant.tobytes()
            if key in seen:
                continue
            seen.add(key)

            feature_sequence = build_feature_sequence(variant, augment=False)
            if feature_sequence.shape == (TARGET_FRAMES, FEATURE_DIM):
                features.append(feature_sequence)

        return features

    def choose_region_token(self, region_predictions: List[Dict], region_start: int, region_end: int):
        if not region_predictions:
            return None

        grouped = {}
        for item in region_predictions:
            grouped.setdefault(item["label"], []).append(item)

        scored = []
        for label, items in grouped.items():
            confidences = [entry["confidence"] for entry in items]
            mean_conf = float(sum(confidences) / len(confidences))
            peak_conf = float(max(confidences))
            score = 0.7 * mean_conf + 0.3 * peak_conf
            scored.append((score, label, mean_conf, peak_conf, items))

        scored.sort(reverse=True)
        _, label, mean_conf, peak_conf, items = scored[0]
        if peak_conf < PREDICTION_CONFIDENCE_THRESHOLD and mean_conf < max(0.50, PREDICTION_CONFIDENCE_THRESHOLD - 0.08):
            return None

        return {
            "label": label,
            "confidence": peak_conf,
            "start": region_start,
            "end": region_end,
        }

    def predict_sentence(self, video_path: str):
        total_start = time.perf_counter()
        print(f"[Timing][LSTM] predict_sentence_start video={video_path}")

        step_start = time.perf_counter()
        frames = self.load_video_frames(video_path)
        self.last_frame_count = len(frames)
        print(f"[Timing][LSTM] load_video_frames={time.perf_counter() - step_start:.3f}s frames={len(frames)}")
        if not frames:
            return ""

        step_start = time.perf_counter()
        raw_sequence = extract_hand_pose_landmarks_from_video(video_path)
        print(f"[Timing][LSTM] mediapipe_landmarks={time.perf_counter() - step_start:.3f}s raw_shape={raw_sequence.shape}")

        step_start = time.perf_counter()
        cut_points = self.find_cut_points(frames)
        print(f"[Timing][LSTM] find_cut_points={time.perf_counter() - step_start:.3f}s cuts={len(cut_points)}")

        step_start = time.perf_counter()
        regions = self.build_cut_regions(len(raw_sequence), cut_points)
        print(f"[Timing][LSTM] build_regions={time.perf_counter() - step_start:.3f}s regions={regions}")

        if not regions:
             regions = [(0, len(raw_sequence))]

        all_sentence_tokens = []
        window_total = 0.0
        for index, (region_start, region_end) in enumerate(regions, start=1):
            step_start = time.perf_counter()
            region_predictions = self.make_window_predictions(raw_sequence, region_start, region_end)
            region_elapsed = time.perf_counter() - step_start
            window_total += region_elapsed
            print(
                f"[Timing][LSTM] region_{index}_window_predictions={region_elapsed:.3f}s "
                f"region=({region_start},{region_end}) predictions={len(region_predictions)}"
            )

            step_start = time.perf_counter()
            chosen = self.choose_region_token(region_predictions, region_start, region_end)
            print(f"[Timing][LSTM] region_{index}_choose_token={time.perf_counter() - step_start:.3f}s chosen={chosen}")
            if chosen is not None:
                all_sentence_tokens.append(chosen)

        print(f"[Timing][LSTM] all_regions_window_total={window_total:.3f}s")

        # Merge neighbor tokens with same label
        if not all_sentence_tokens:
            print(f"[Timing][LSTM] total_predict={time.perf_counter() - total_start:.3f}s sentence_empty=True")
            return ""

        step_start = time.perf_counter()
        merged_tokens = []
        for item in all_sentence_tokens:
            if not merged_tokens:
                merged_tokens.append(item)
                continue
            prev = merged_tokens[-1]
            if item["label"] == prev["label"]:
                prev["end"] = max(prev["end"], item["end"])
                prev["confidence"] = max(prev["confidence"], item["confidence"])
            else:
                merged_tokens.append(item)

        sentence = " ".join([t["label"] for t in merged_tokens]).upper()
        print(f"[Timing][LSTM] merge_tokens={time.perf_counter() - step_start:.3f}s tokens={len(merged_tokens)}")
        print(f"[Timing][LSTM] total_predict={time.perf_counter() - total_start:.3f}s sentence={sentence}")
        return sentence
