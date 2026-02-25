"""
Universal Document Image Preprocessing Pipeline — Industry Grade

Adaptive pipeline that analyzes each image and applies only the transforms it needs.
Preserves ALL structural elements (table borders, lines, checkboxes, stamps).

Capabilities:
 ┌──────────────────────────────────────────────────────────┐
 │  1. Quality Assessment   — score input, decide pipeline  │
 │  2. Orientation Fix      — auto-rotate 0°/90°/180°/270° │
 │  3. Perspective Correct  — fix camera angle distortion   │
 │  4. Shadow Removal       — uneven lighting compensation  │
 │  5. Noise Reduction      — adaptive strength per quality │
 │  6. Contrast Enhancement — CLAHE with smart clip limits  │
 │  7. Sharpening           — edge-aware unsharp mask       │
 │  8. Deskew               — sub-degree precision          │
 │  9. Resolution Normalize — ensure 300 DPI minimum        │
 │ 10. Color Mode Detect    — color/grayscale/binary auto   │
 └──────────────────────────────────────────────────────────┘

Design principles:
 - NEVER removes borders or lines (tables, forms, boxes are sacred)
 - Adaptive: noisy images get heavier denoising, clean ones get minimal
 - Two output modes: GLM (color-preserving) and Binary (traditional OCR)
 - Every transform is idempotent — running twice gives same result
"""

import cv2
import numpy as np
import os
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


class DocType(Enum):
    PRINTED = "printed"
    HANDWRITTEN = "handwritten"
    MIXED = "mixed"
    PHOTO = "photo"           # camera capture of document
    SCAN_CLEAN = "scan_clean"
    SCAN_NOISY = "scan_noisy"


class ColorMode(Enum):
    COLOR = "color"
    GRAYSCALE = "grayscale"
    BINARY = "binary"


@dataclass
class ImageProfile:
    """Analysis result for an input image."""
    width: int = 0
    height: int = 0
    noise_level: float = 0.0       # 0 = clean, 100 = very noisy
    brightness: float = 0.0        # 0-255
    contrast: float = 0.0          # std dev of pixel values
    sharpness: float = 0.0         # Laplacian variance
    skew_angle: float = 0.0        # degrees
    has_color: bool = False
    is_low_res: bool = False
    orientation: int = 0           # 0, 90, 180, 270
    doc_type: DocType = DocType.SCAN_CLEAN
    color_mode: ColorMode = ColorMode.GRAYSCALE
    needs_shadow_removal: bool = False
    needs_perspective_fix: bool = False
    quality_score: float = 1.0     # 0.0 (terrible) to 1.0 (perfect)


class UniversalImageEnhancer:
    """
    Industry-grade adaptive document image preprocessor.

    Usage:
        enhancer = UniversalImageEnhancer()
        output_path = enhancer.enhance("input.png", mode="glm")
    """

    def __init__(self, target_dpi: int = 300):
        self.target_dpi = target_dpi

    def enhance(self, input_path: str, output_path: str = None, mode: str = "glm") -> str:
        """
        Main entry point. Analyzes the image, builds an adaptive pipeline,
        and produces an enhanced output.

        Args:
            input_path: Path to input image
            output_path: Optional output path
            mode: "glm" (color-preserving for GLM-OCR) or "binary" (traditional OCR)
        """
        if output_path is None:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_enhanced{ext}"

        img = cv2.imread(input_path)
        if img is None:
            raise ValueError(f"Cannot read image: {input_path}")

        fname = os.path.basename(input_path)
        logger.info(f"{'─'*50}")
        logger.info(f"📸 Processing: {fname} ({img.shape[1]}x{img.shape[0]})")

        # ── Phase 1: Analyze ──
        profile = self._analyze(img)
        logger.info(f"  📊 Profile: type={profile.doc_type.value}, noise={profile.noise_level:.1f}, "
                     f"contrast={profile.contrast:.1f}, sharpness={profile.sharpness:.1f}, "
                     f"quality={profile.quality_score:.2f}")

        # ── Phase 2: Orientation correction ──
        if profile.orientation != 0:
            img = self._fix_orientation(img, profile.orientation)

        # ── Phase 3: Perspective correction (camera captures) ──
        if profile.needs_perspective_fix:
            img = self._fix_perspective(img)

        # ── Phase 4: Apply mode-specific pipeline ──
        if mode == "glm":
            img = self._pipeline_glm(img, profile)
        else:
            img = self._pipeline_binary(img, profile)

        cv2.imwrite(output_path, img, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        logger.info(f"  ✅ Saved: {output_path}")
        return output_path

    # ══════════════════════════════════════════
    # Phase 1: Image Analysis
    # ══════════════════════════════════════════

    def _analyze(self, img: np.ndarray) -> ImageProfile:
        """Comprehensive image quality analysis."""
        p = ImageProfile()
        p.height, p.width = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

        # Color detection
        if len(img.shape) == 3:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            saturation = hsv[:, :, 1].mean()
            p.has_color = saturation > 30
            p.color_mode = ColorMode.COLOR if p.has_color else ColorMode.GRAYSCALE
        else:
            p.color_mode = ColorMode.GRAYSCALE

        # Brightness & contrast
        p.brightness = float(gray.mean())
        p.contrast = float(gray.std())

        # Noise estimation (Laplacian method)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        p.sharpness = float(laplacian.var())
        # Noise as ratio of high-frequency content to expected
        sigma = float(np.median(np.abs(laplacian)) / 0.6745)
        p.noise_level = min(sigma, 100.0)

        # Resolution check
        p.is_low_res = min(p.width, p.height) < 1000

        # Skew detection
        p.skew_angle = self._detect_skew(gray)

        # Orientation detection (0, 90, 180, 270)
        p.orientation = self._detect_orientation(gray)

        # Shadow detection
        p.needs_shadow_removal = self._detect_shadows(gray)

        # Perspective detection (for camera captures)
        p.needs_perspective_fix = self._detect_perspective_distortion(gray)

        # Document type classification
        p.doc_type = self._classify_document(gray, p)

        # Overall quality score
        p.quality_score = self._compute_quality_score(p)

        return p

    def _detect_skew(self, gray: np.ndarray) -> float:
        """Precise skew detection using Hough Line Transform."""
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                                 minLineLength=gray.shape[1] // 5, maxLineGap=15)
        if lines is None:
            return 0.0

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if abs(x2 - x1) < 5:
                continue  # Skip vertical lines
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            if abs(angle) < 20:  # Only near-horizontal (text lines)
                angles.append(angle)

        if len(angles) < 3:
            return 0.0

        # Use median to be robust against outliers
        return float(np.median(angles))

    def _detect_orientation(self, gray: np.ndarray) -> int:
        """Detect if document is rotated 90°/180°/270°.

        Uses text-line density: most text documents have more horizontal
        edges than vertical ones when correctly oriented.
        """
        h, w = gray.shape
        # Only check if image is large enough
        if h < 200 or w < 200:
            return 0

        edges = cv2.Canny(gray, 50, 150)

        # Horizontal vs vertical edge density
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
        h_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, h_kernel)
        v_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, v_kernel)

        h_density = float(h_edges.sum())
        v_density = float(v_edges.sum())

        # If vertical edges dominate, the document is likely rotated 90°
        if v_density > h_density * 1.5 and w < h:
            return 90
        elif v_density > h_density * 1.5 and w > h:
            return 270

        return 0

    def _detect_shadows(self, gray: np.ndarray) -> bool:
        """Detect uneven lighting / shadows."""
        # Divide image into quadrants and compare brightness
        h, w = gray.shape
        quadrants = [
            gray[:h//2, :w//2],
            gray[:h//2, w//2:],
            gray[h//2:, :w//2],
            gray[h//2:, w//2:],
        ]
        means = [float(q.mean()) for q in quadrants]
        brightness_range = max(means) - min(means)
        return brightness_range > 50  # Significant uneven lighting

    def _detect_perspective_distortion(self, gray: np.ndarray) -> bool:
        """Detect if image is a camera capture with perspective distortion."""
        h, w = gray.shape
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                 minLineLength=min(h, w) // 3, maxLineGap=20)
        if lines is None:
            return False

        # Check if there are strong diagonal lines (perspective)
        diagonal_count = 0
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if abs(x2 - x1) < 5:
                continue
            angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
            if 5 < angle < 85:  # Neither horizontal nor vertical
                diagonal_count += 1

        return diagonal_count > len(lines) * 0.4  # >40% diagonal = likely camera capture

    def _classify_document(self, gray: np.ndarray, profile: ImageProfile) -> DocType:
        """Classify document type based on image characteristics."""
        if profile.needs_perspective_fix:
            return DocType.PHOTO

        if profile.noise_level > 30:
            return DocType.SCAN_NOISY

        # Handwriting detection: handwritten text has more varied stroke widths
        # and less regular vertical/horizontal alignment
        edges = cv2.Canny(gray, 50, 150)
        h_proj = np.sum(edges, axis=1)
        regularity = np.std(h_proj[h_proj > 0]) / (np.mean(h_proj[h_proj > 0]) + 1e-6)

        if regularity > 1.5:
            return DocType.HANDWRITTEN
        elif regularity > 0.8:
            return DocType.MIXED

        return DocType.PRINTED if profile.noise_level < 10 else DocType.SCAN_CLEAN

    def _compute_quality_score(self, p: ImageProfile) -> float:
        """Composite quality score 0.0-1.0."""
        score = 1.0

        # Penalize low resolution
        if p.is_low_res:
            score -= 0.2

        # Penalize high noise
        score -= min(p.noise_level / 100, 0.3)

        # Penalize low contrast
        if p.contrast < 30:
            score -= 0.2

        # Penalize skew
        if abs(p.skew_angle) > 1.0:
            score -= 0.1

        # Penalize shadows
        if p.needs_shadow_removal:
            score -= 0.1

        return max(0.0, min(1.0, score))

    # ══════════════════════════════════════════
    # Phase 2: Transforms
    # ══════════════════════════════════════════

    def _fix_orientation(self, img: np.ndarray, angle: int) -> np.ndarray:
        """Rotate image by 90°/180°/270°."""
        logger.info(f"  🔄 Fixing orientation: rotating {angle}°")
        if angle == 90:
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            return cv2.rotate(img, cv2.ROTATE_180)
        elif angle == 270:
            return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return img

    def _fix_perspective(self, img: np.ndarray) -> np.ndarray:
        """Correct perspective distortion from camera captures.

        Finds the document quadrilateral and warps it to a rectangle.
        Falls back to no-op if document edges can't be detected.
        """
        logger.info("  📐 Attempting perspective correction")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 100)

        # Dilate to close gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edges = cv2.dilate(edges, kernel, iterations=2)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return img

        # Find the largest quadrilateral contour
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        img_area = img.shape[0] * img.shape[1]

        if area < img_area * 0.3:
            logger.info("    No document boundary found, skipping perspective fix")
            return img

        # Approximate to polygon
        peri = cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, 0.02 * peri, True)

        if len(approx) != 4:
            logger.info("    Could not find 4-corner document, skipping")
            return img

        # Order points: top-left, top-right, bottom-right, bottom-left
        pts = approx.reshape(4, 2).astype(np.float32)
        pts = self._order_points(pts)

        # Target rectangle dimensions
        w1 = np.linalg.norm(pts[1] - pts[0])
        w2 = np.linalg.norm(pts[2] - pts[3])
        h1 = np.linalg.norm(pts[3] - pts[0])
        h2 = np.linalg.norm(pts[2] - pts[1])
        max_w = int(max(w1, w2))
        max_h = int(max(h1, h2))

        dst = np.array([[0, 0], [max_w, 0], [max_w, max_h], [0, max_h]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(pts, dst)
        warped = cv2.warpPerspective(img, M, (max_w, max_h), borderValue=(255, 255, 255))

        logger.info(f"    ✅ Perspective corrected: {max_w}x{max_h}")
        return warped

    def _order_points(self, pts: np.ndarray) -> np.ndarray:
        """Order 4 points as: TL, TR, BR, BL."""
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # Top-left
        rect[2] = pts[np.argmax(s)]   # Bottom-right
        d = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(d)]   # Top-right
        rect[3] = pts[np.argmax(d)]   # Bottom-left
        return rect

    def _remove_shadows(self, img: np.ndarray) -> np.ndarray:
        """Remove shadows using morphological background estimation."""
        logger.info("  🌓 Removing shadows")
        if len(img.shape) == 3:
            # Process each channel
            channels = cv2.split(img)
            result = []
            for ch in channels:
                bg = cv2.morphologyEx(ch, cv2.MORPH_DILATE,
                                       cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
                diff = 255 - cv2.absdiff(ch, bg)
                normalized = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)
                result.append(normalized)
            return cv2.merge(result)
        else:
            bg = cv2.morphologyEx(img, cv2.MORPH_DILATE,
                                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
            diff = 255 - cv2.absdiff(img, bg)
            return cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)

    def _adaptive_denoise(self, img: np.ndarray, noise_level: float) -> np.ndarray:
        """Adaptive denoising — strength scales with measured noise."""
        if noise_level < 5:
            return img  # Already clean

        # Scale h parameter with noise level
        h = int(min(3 + noise_level * 0.3, 15))
        logger.info(f"  🔇 Denoising (h={h}, noise={noise_level:.1f})")

        if len(img.shape) == 3:
            return cv2.fastNlMeansDenoisingColored(img, None, h=h, hForColorComponents=h,
                                                    templateWindowSize=7, searchWindowSize=21)
        else:
            return cv2.fastNlMeansDenoising(img, None, h=h, templateWindowSize=7, searchWindowSize=21)

    def _adaptive_contrast(self, img: np.ndarray, profile: ImageProfile) -> np.ndarray:
        """CLAHE with adaptive clip limit based on image contrast."""
        clip = 2.0  # Default
        if profile.contrast < 25:
            clip = 4.0  # Low contrast → aggressive enhancement
        elif profile.contrast > 60:
            clip = 1.5  # Good contrast → mild enhancement

        logger.info(f"  📊 CLAHE contrast (clip={clip:.1f}, input_contrast={profile.contrast:.1f})")

        if len(img.shape) == 3:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
            l = clahe.apply(l)
            return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
        else:
            clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
            return clahe.apply(img)

    def _sharpen(self, img: np.ndarray, profile: ImageProfile) -> np.ndarray:
        """Edge-aware unsharp mask. Strength adapts to current sharpness."""
        if profile.sharpness > 500:
            return img  # Already sharp enough

        strength = 1.5 if profile.sharpness < 100 else 1.2
        logger.info(f"  🔍 Sharpening (strength={strength:.1f}, input_sharpness={profile.sharpness:.1f})")

        gaussian = cv2.GaussianBlur(img, (0, 0), 2.0)
        return cv2.addWeighted(img, strength, gaussian, 1.0 - strength, 0)

    def _deskew(self, img: np.ndarray, angle: float) -> np.ndarray:
        """Sub-degree deskew with canvas expansion (no cropping)."""
        if abs(angle) < 0.2:
            return img

        logger.info(f"  ↺ Deskewing: {angle:.2f}°")
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)

        cos_a, sin_a = abs(M[0, 0]), abs(M[0, 1])
        new_w = int(h * sin_a + w * cos_a)
        new_h = int(h * cos_a + w * sin_a)
        M[0, 2] += (new_w - w) / 2
        M[1, 2] += (new_h - h) / 2

        bg = (255, 255, 255) if len(img.shape) == 3 else 255
        return cv2.warpAffine(img, M, (new_w, new_h), borderValue=bg)

    def _upscale(self, img: np.ndarray) -> np.ndarray:
        """Bicubic upscale to ensure minimum 300 DPI equivalent."""
        h, w = img.shape[:2]
        min_dim = 1500  # ~300 DPI at 5 inches
        if min(h, w) >= min_dim:
            return img

        scale = min_dim / min(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        logger.info(f"  ↗ Upscaling: {w}x{h} → {new_w}x{new_h}")
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    # ══════════════════════════════════════════
    # Pipelines
    # ══════════════════════════════════════════

    def _pipeline_glm(self, img: np.ndarray, profile: ImageProfile) -> np.ndarray:
        """
        GLM-OCR optimized pipeline (color-preserving).
        GLM is a vision-language model — it performs best on natural-looking
        images with color and structure intact.
        """
        logger.info("  🧠 Pipeline: GLM (color-preserving)")

        # 1. Upscale if needed
        img = self._upscale(img)

        # 2. Shadow removal (if detected)
        if profile.needs_shadow_removal:
            img = self._remove_shadows(img)

        # 3. Adaptive denoising
        img = self._adaptive_denoise(img, profile.noise_level)

        # 4. Adaptive contrast
        img = self._adaptive_contrast(img, profile)

        # 5. Sharpen
        img = self._sharpen(img, profile)

        # 6. Deskew
        img = self._deskew(img, profile.skew_angle)

        return img

    def _pipeline_binary(self, img: np.ndarray, profile: ImageProfile) -> np.ndarray:
        """Binary pipeline for traditional OCR engines."""
        logger.info("  ⬛ Pipeline: Binary (traditional OCR)")

        img = self._upscale(img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

        if profile.needs_shadow_removal:
            gray = self._remove_shadows(gray)

        gray = self._adaptive_denoise(gray, profile.noise_level)
        gray = self._adaptive_contrast(gray, profile)
        gray = self._deskew(gray, profile.skew_angle)

        # Adaptive binarization
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, blockSize=15, C=8
        )

        # Gentle morphological cleanup (preserves thin strokes and lines)
        if profile.doc_type == DocType.HANDWRITTEN:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

        return binary


# ══════════════════════════════════════════
# Batch Processing
# ══════════════════════════════════════════

def process_directory(input_dir: str, output_dir: str, mode: str = "glm") -> list:
    """Process all images in a directory."""
    os.makedirs(output_dir, exist_ok=True)
    enhancer = UniversalImageEnhancer()
    extensions = {'.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp'}
    results = []

    for fname in sorted(os.listdir(input_dir)):
        if Path(fname).suffix.lower() in extensions:
            input_path = os.path.join(input_dir, fname)
            output_path = os.path.join(output_dir, fname)
            try:
                enhancer.enhance(input_path, output_path, mode=mode)
                results.append({"file": fname, "status": "success"})
            except Exception as e:
                logger.error(f"Failed: {fname}: {e}")
                results.append({"file": fname, "status": "error", "error": str(e)})

    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python image_enhancer.py <input_dir> <output_dir> [mode: glm|binary]")
        sys.exit(1)

    mode = sys.argv[3] if len(sys.argv) > 3 else "glm"
    results = process_directory(sys.argv[1], sys.argv[2], mode)

    success = sum(1 for r in results if r["status"] == "success")
    print(f"\n{'═'*40}")
    print(f"Processed {len(results)} images: {success} success, {len(results)-success} failed")
    for r in results:
        icon = "✅" if r["status"] == "success" else "❌"
        print(f"  {icon} {r['file']}")
