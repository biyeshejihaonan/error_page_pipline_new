import subprocess
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image


RENDER_DPI = 300
MINERU_REFERENCE_WIDTH = 1024
ROW_CROP_PADDING = 2


def _bbox_reference_size(image_width: int, image_height: int, bbox: list[int]) -> tuple[int, int]:
    if len(bbox) != 4:
        return image_width, image_height
    if bbox[2] <= image_width and bbox[3] <= image_height:
        return image_width, image_height
    reference_width = max(MINERU_REFERENCE_WIDTH, bbox[2] + 64)
    reference_height = round(reference_width * image_height / image_width)
    return reference_width, reference_height


def _scale_bbox_to_image(image_width: int, image_height: int, bbox: list[int]) -> tuple[int, int, int, int]:
    if len(bbox) != 4:
        return 0, 0, image_width, image_height
    ref_width, ref_height = _bbox_reference_size(image_width, image_height, bbox)
    scale_x = image_width / ref_width
    scale_y = image_height / ref_height
    left = max(0, min(image_width - 1, int(bbox[0] * scale_x)))
    top = max(0, min(image_height - 1, int(bbox[1] * scale_y)))
    right = max(left + 1, min(image_width, int(bbox[2] * scale_x)))
    bottom = max(top + 1, min(image_height, int(bbox[3] * scale_y)))
    return left, top, right, bottom


def render_split_pdf_to_png(split_page_pdf: Optional[Path], output_dir: Path) -> Optional[Path]:
    if split_page_pdf is None or not split_page_pdf.exists():
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / (split_page_pdf.stem + ".png")
    if output_path.exists():
        with Image.open(output_path) as existing:
            if existing.width >= 1500:
                return output_path

    subprocess.run(
        [
            "/opt/homebrew/bin/pdftoppm",
            "-singlefile",
            "-png",
            "-r",
            str(RENDER_DPI),
            str(split_page_pdf),
            str(output_path.with_suffix("")),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path if output_path.exists() else None


def crop_table_regions(
    rendered_page_image: Optional[Path],
    output_dir: Path,
    page_stem: str,
    bboxes: Iterable[list[int]],
) -> list[Path]:
    if rendered_page_image is None or not rendered_page_image.exists():
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(rendered_page_image)
    saved_paths: list[Path] = []
    for index, bbox in enumerate(bboxes):
        left, top, right, bottom = _scale_bbox_to_image(image.width, image.height, bbox)
        crop_path = output_dir / f"{page_stem}_table_{index}.png"
        image.crop((left, top, right, bottom)).save(crop_path)
        saved_paths.append(crop_path)
    image.close()
    return saved_paths


def crop_row_region(
    rendered_page_image: Optional[Path],
    output_dir: Path,
    page_stem: str,
    bbox: list[int],
    row_index: int,
    row_count: int,
) -> Optional[Path]:
    if rendered_page_image is None or not rendered_page_image.exists() or row_count <= 0:
        return None
    image = Image.open(rendered_page_image)
    left, top, right, bottom = _scale_bbox_to_image(image.width, image.height, bbox)
    table_height = max(1, bottom - top)
    row_height = table_height / max(row_count, 1)
    row_top = top + int(max(0, row_index - ROW_CROP_PADDING) * row_height)
    row_bottom = top + int(min(row_count, row_index + ROW_CROP_PADDING + 1) * row_height)
    row_top = max(0, min(image.height - 1, row_top))
    row_bottom = max(row_top + 1, min(image.height, row_bottom))
    output_dir.mkdir(parents=True, exist_ok=True)
    crop_path = output_dir / f"{page_stem}_row_{row_index}.png"
    image.crop((left, row_top, right, row_bottom)).save(crop_path)
    image.close()
    return crop_path
