import subprocess
from pathlib import Path
from typing import Optional


def render_split_pdf_to_png(split_page_pdf: Optional[Path], output_dir: Path) -> Optional[Path]:
    if split_page_pdf is None or not split_page_pdf.exists():
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / (split_page_pdf.stem + ".png")
    if output_path.exists():
        return output_path

    subprocess.run(
        [
            "/usr/bin/sips",
            "-s",
            "format",
            "png",
            str(split_page_pdf),
            "--out",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path if output_path.exists() else None
