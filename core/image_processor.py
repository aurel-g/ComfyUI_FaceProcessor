import cv2
import numpy as np
import pandas as pd
import torch
from PIL import Image
from typing import Union, Optional, Tuple

class ImageProcessor:
    @staticmethod
    def _convert_to_numpy(image: Union[torch.Tensor, np.ndarray, Image.Image]) -> np.ndarray:
        """Convert different image types to numpy array."""
        if torch.is_tensor(image):
            image = image.detach().cpu().numpy()
            if len(image.shape) == 4:
                image = image[0]
            image = (image * 255).astype(np.uint8)
        elif isinstance(image, Image.Image):
            image = np.array(image)
        elif isinstance(image, np.ndarray):
            if image.dtype == np.float32 and image.max() <= 1.0:
                image = (image * 255).astype(np.uint8)
            if len(image.shape) == 4:
                image = image[0]

        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)

        return image

    @staticmethod
    def calculate_face_bbox(landmarks_df: pd.DataFrame, padding_percent: float = 0.0) -> Optional[Tuple[int, int, int, int]]:
        """Calculate bounding box for face based on landmarks."""
        if landmarks_df is None or landmarks_df.empty:
            return None

        min_x = landmarks_df['x'].min()
        max_x = landmarks_df['x'].max()
        min_y = landmarks_df['y'].min()
        max_y = landmarks_df['y'].max()

        width = max_x - min_x
        height = max_y - min_y

        pad_x = width * padding_percent
        pad_y = height * padding_percent

        x1 = max(0, min_x - pad_x)
        y1 = max(0, min_y - pad_y)
        x2 = max_x + pad_x
        y2 = max_y + pad_y

        return (int(x1), int(y1), int(x2 - x1), int(y2 - y1))

    @staticmethod
    def crop_face(image: Union[torch.Tensor, np.ndarray, Image.Image], landmarks_df: pd.DataFrame, padding_percent: float = 0.0) -> Optional[np.ndarray]:
        """Crop face region from image based on landmarks."""
        image_np = ImageProcessor._convert_to_numpy(image)
        bbox = ImageProcessor.calculate_face_bbox(landmarks_df, padding_percent)

        if bbox is None:
            return None

        x, y, w, h = bbox
        return image_np[y:y + h, x:x + w]

    @staticmethod
    def resize_image(image: Union[torch.Tensor, np.ndarray, Image.Image], target_size: int) -> Optional[np.ndarray]:
        """Resize image to target size while maintaining aspect ratio and cropping to square."""
        if image is None:
            return None

        image_np = ImageProcessor._convert_to_numpy(image)
        h, w = image_np.shape[:2]

        # Determine the smaller dimension (height or width)
        min_dim = min(h, w)

        # Calculate the crop box to make the image square
        start_x = (w - min_dim) // 2
        start_y = (h - min_dim) // 2
        end_x = start_x + min_dim
        end_y = start_y + min_dim

        # Crop the image to a square
        cropped_image = image_np[start_y:end_y, start_x:end_x]

        # Resize the cropped image to the target size
        resized = cv2.resize(cropped_image, (target_size, target_size), interpolation=cv2.INTER_LANCZOS4)

        return resized

    @staticmethod
    def calculate_rotation_angle(landmarks_df: pd.DataFrame) -> float:
        """Calculate rotation angle based on eyes position."""
        if landmarks_df is None or landmarks_df.empty:
            return 0.0

        LEFT_EYE = 33  # Center of the left eye
        RIGHT_EYE = 263  # Center of the right eye

        left_eye = landmarks_df[landmarks_df['index'] == LEFT_EYE].iloc[0]
        right_eye = landmarks_df[landmarks_df['index'] == RIGHT_EYE].iloc[0]

        dx = right_eye['x'] - left_eye['x']
        dy = right_eye['y'] - left_eye['y']
        return np.degrees(np.arctan2(dy, dx))

    @staticmethod
    def rotate_image(image: Union[torch.Tensor, np.ndarray, Image.Image], landmarks_df: pd.DataFrame) -> Tuple[Optional[np.ndarray], Optional[pd.DataFrame]]:
        """Rotate image based on facial landmarks."""
        image_np = ImageProcessor._convert_to_numpy(image)

        if image_np is None or landmarks_df is None:
            return None, None

        angle = ImageProcessor.calculate_rotation_angle(landmarks_df)
        height, width = image_np.shape[:2]
        center = (width // 2, height // 2)

        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated_image = cv2.warpAffine(image_np, rotation_matrix, (width, height), flags=cv2.INTER_LANCZOS4)

        # Transform landmarks
        ones = np.ones(shape=(len(landmarks_df), 1))
        points = np.hstack([landmarks_df[['x', 'y']].values, ones])
        transformed_points = rotation_matrix.dot(points.T).T

        updated_landmarks = landmarks_df.copy()
        updated_landmarks['x'] = transformed_points[:, 0]
        updated_landmarks['y'] = transformed_points[:, 1]

        return rotated_image, updated_landmarks

    @staticmethod
    def crop_face_to_square(image: np.ndarray, landmarks_df: pd.DataFrame, padding_percent: float = 0.0) -> Tuple[
        Optional[np.ndarray], Optional[Tuple[int, int, int, int]]]:
        """Crop face region to a square (1:1) based on landmarks."""
        bbox = ImageProcessor.calculate_face_bbox(landmarks_df, padding_percent)
        if bbox is None:
            return None, None

        x, y, w, h = bbox

        # Calculate the center of the bounding box
        center_x = x + w // 2
        center_y = y + h // 2

        # Determine the size of the square crop
        crop_size = max(w, h)
        half_size = crop_size // 2

        # Calculate the crop coordinates
        x1 = max(0, center_x - half_size)
        y1 = max(0, center_y - half_size)
        x2 = min(image.shape[1], center_x + half_size)
        y2 = min(image.shape[0], center_y + half_size)

        # Adjust if the crop goes out of bounds
        if x2 - x1 < crop_size:
            x1 = max(0, x2 - crop_size)
        if y2 - y1 < crop_size:
            y1 = max(0, y2 - crop_size)

        # Crop the image
        cropped_face = image[y1:y2, x1:x2]

        # Return the cropped face and the crop bounding box
        return cropped_face, (x1, y1, x2 - x1, y2 - y1)
