"""PDF 文件读取工具（多后端稳健版：文本层 / PyMuPDF / OCR / 表格分区）"""
from __future__ import annotations

import io
import shutil
from typing import List, Optional, Sequence, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from pypdf import PdfReader

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat
except Exception:  # pragma: no cover
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None
    ImageStat = None


class PDFReadError(Exception):
    """PDF 读取异常。"""


# -------------------------
# 基础安全工具
# -------------------------
def _normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return "\n".join(line.rstrip() for line in text.replace("\x0c", "\n").splitlines()).strip()


def _safe_join_text(parts: Sequence[str]) -> str:
    clean = [p for p in (_normalize_text(x) for x in parts) if p]
    return "\n\n".join(clean)


def _safe_pdf_page_count(reader: PdfReader) -> int:
    try:
        count = len(reader.pages)
    except Exception as e:
        raise PDFReadError(f"无法读取 PDF 页数，文件可能已损坏或结构异常：{e}")
    if count <= 0:
        raise PDFReadError("PDF 中没有可读取的页面")
    return count


def _safe_extract_text_from_reader(reader: PdfReader) -> tuple[str, List[str]]:
    """优先从 PDF 文本层提取内容，单页失败不影响整份文件。"""
    text_parts: List[str] = []
    page_errors: List[str] = []

    page_count = _safe_pdf_page_count(reader)

    for i in range(page_count):
        try:
            if i < 0 or i >= page_count:
                page_errors.append(f"第 {i + 1} 页索引越界，已跳过")
                continue
            page = reader.pages[i]
            text = _normalize_text(page.extract_text())
            if text:
                text_parts.append(text)
        except Exception as e:
            page_errors.append(f"第 {i + 1} 页文本层读取失败: {e}")

    return _safe_join_text(text_parts), page_errors


# -------------------------
# OCR 语言与图像质量判断
# -------------------------
def _pick_ocr_languages() -> str:
    """选择当前环境下可用的 OCR 语言包。"""
    if pytesseract is None:
        return "eng"

    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception:
        langs = set()

    preferred = ["chi_sim", "chi_tra", "HanS", "eng"]
    selected = [lang for lang in preferred if lang in langs]
    return "+".join(selected) if selected else "eng"


def _text_score(text: str) -> int:
    text = _normalize_text(text)
    if not text:
        return 0
    useful = sum(ch.isalnum() or ('\u4e00' <= ch <= '\u9fff') for ch in text)
    lines = len([ln for ln in text.splitlines() if ln.strip()])
    penalty = text.count("�") * 5
    return useful + lines * 3 - penalty


def _image_is_too_blank(image: Image.Image) -> bool:
    try:
        gray = image.convert("L")
        stat = ImageStat.Stat(gray)
        stddev = stat.stddev[0] if stat.stddev else 0
        return stddev < 4
    except Exception:
        return False


# -------------------------
# 图像增强 / 纠偏 / 去噪
# -------------------------
def _maybe_upscale(image: Image.Image, min_side: int = 1600) -> Image.Image:
    try:
        w, h = image.size
        short_side = min(w, h)
        if short_side >= min_side:
            return image
        scale = min_side / max(1, short_side)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        return image.resize(new_size, Image.Resampling.LANCZOS)
    except Exception:
        return image


def _crop_header_footer(image: Image.Image, top_ratio: float = 0.06, bottom_ratio: float = 0.08) -> Image.Image:
    """轻量去掉常见页眉页脚区域，减少 OCR 干扰。"""
    try:
        w, h = image.size
        if h < 400:
            return image
        top = int(h * max(0.0, min(0.15, top_ratio)))
        bottom = int(h * max(0.0, min(0.18, bottom_ratio)))
        if top + bottom >= h - 20:
            return image
        cropped = image.crop((0, top, w, h - bottom))
        return cropped if cropped.size[1] > 50 else image
    except Exception:
        return image


def _basic_denoise(image: Image.Image) -> Image.Image:
    try:
        img = image.convert("L")
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(1.6)
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = img.filter(ImageFilter.SHARPEN)
        return img
    except Exception:
        return image


def _binary_variants(image: Image.Image) -> List[Image.Image]:
    variants: List[Image.Image] = []
    try:
        gray = image.convert("L")
        for threshold in (150, 180):
            variants.append(gray.point(lambda p, t=threshold: 255 if p > t else 0, mode="1").convert("L"))
    except Exception:
        pass
    return variants


def _detect_rotation_osd(image: Image.Image) -> int:
    if pytesseract is None:
        return 0
    try:
        osd = pytesseract.image_to_osd(image)
        for line in osd.splitlines():
            if "Rotate:" in line:
                return int(line.split(":", 1)[1].strip())
    except Exception:
        return 0
    return 0


def _apply_rotation(image: Image.Image, angle: int) -> Image.Image:
    try:
        angle = angle % 360
        if angle == 0:
            return image
        # tesseract OSD 的 Rotate 含义是需要旋转多少度校正
        return image.rotate(-angle, expand=True, fillcolor="white")
    except Exception:
        return image


def _prepare_ocr_images(image: Image.Image) -> List[Tuple[str, Image.Image]]:
    """生成多组 OCR 候选图像。"""
    prepared: List[Tuple[str, Image.Image]] = []

    try:
        base = _maybe_upscale(image)
        base = _basic_denoise(base)

        # 原图增强版
        prepared.append(("enhanced_full", base))

        # 页眉页脚去噪版
        cropped = _crop_header_footer(base)
        prepared.append(("enhanced_cropped", cropped))

        # 二值化版本
        for idx, img in enumerate(_binary_variants(base), start=1):
            prepared.append((f"binary_full_{idx}", img))
        for idx, img in enumerate(_binary_variants(cropped), start=1):
            prepared.append((f"binary_cropped_{idx}", img))
    except Exception:
        prepared.append(("fallback", image))

    # 去重，避免同尺寸同对象重复过多
    unique: List[Tuple[str, Image.Image]] = []
    seen = set()
    for name, img in prepared:
        key = (name.split("_")[0], getattr(img, "size", None))
        if key in seen and len(unique) >= 4:
            continue
        seen.add(key)
        unique.append((name, img))
    return unique[:8]


def _ocr_single_image(image: Image.Image, lang: str) -> str:
    configs = (
        "--oem 3 --psm 6",
        "--oem 3 --psm 4",
        "--oem 3 --psm 11",
    )
    candidates: List[str] = []
    for config in configs:
        try:
            txt = _normalize_text(pytesseract.image_to_string(image, lang=lang, config=config))
            if txt:
                candidates.append(txt)
        except Exception:
            continue
    if not candidates:
        return ""
    return max(candidates, key=_text_score)


def _ocr_page_image(image: Image.Image, lang: str) -> str:
    if _image_is_too_blank(image):
        return ""

    # 先做 90/180/270 度自动纠偏
    rotate_angle = _detect_rotation_osd(image)
    deskewed = _apply_rotation(image, rotate_angle)

    best_text = ""
    best_score = -1
    for _name, prepared in _prepare_ocr_images(deskewed):
        text = _ocr_single_image(prepared, lang)
        score = _text_score(text)
        if score > best_score:
            best_text, best_score = text, score

    # 如果裁切版反而损失太大，则再用未裁切原图兜底一次
    if best_score < 10:
        raw_text = _ocr_single_image(_basic_denoise(_maybe_upscale(image)), lang)
        if _text_score(raw_text) > best_score:
            best_text = raw_text

    return _normalize_text(best_text)




# -------------------------
# 表格线检测 / 分区域 OCR
# -------------------------
def _to_gray_array(image: Image.Image):
    if np is None:
        return None
    try:
        return np.array(image.convert("L"))
    except Exception:
        return None


def _find_dense_line_ranges(density, threshold: float, min_run: int) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    start = None
    for idx, value in enumerate(density):
        if value >= threshold and start is None:
            start = idx
        elif value < threshold and start is not None:
            if idx - start >= min_run:
                ranges.append((start, idx - 1))
            start = None
    if start is not None and len(density) - start >= min_run:
        ranges.append((start, len(density) - 1))
    return ranges


def _merge_close_ranges(ranges: List[Tuple[int, int]], gap: int = 8) -> List[Tuple[int, int]]:
    if not ranges:
        return []
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        if start - last_end <= gap:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _detect_table_lines_and_regions(image: Image.Image) -> Tuple[Optional[Image.Image], List[Tuple[int, int, int, int]]]:
    """检测横线/竖线，并输出去线后的图像与阅读区域。"""
    if Image is None:
        return None, []

    gray = _to_gray_array(image)
    if gray is None or gray.size == 0:
        return None, []

    h, w = gray.shape[:2]
    if h < 120 or w < 120:
        return None, []

    try:
        if cv2 is not None:
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            h_kernel_len = max(20, w // 30)
            v_kernel_len = max(20, h // 30)
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_len, 1))
            v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_len))
            h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
            v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
            line_mask = cv2.bitwise_or(h_lines, v_lines)
            line_density_rows = (h_lines > 0).mean(axis=1)
            line_density_cols = (v_lines > 0).mean(axis=0)
        else:
            inv = 255 - gray
            row_dark = (inv > 180).mean(axis=1)
            col_dark = (inv > 180).mean(axis=0)
            line_density_rows = row_dark
            line_density_cols = col_dark
            line_mask = None

        hranges = _merge_close_ranges(
            _find_dense_line_ranges(line_density_rows, threshold=0.35, min_run=max(2, h // 300)),
            gap=max(4, h // 200),
        )
        vranges = _merge_close_ranges(
            _find_dense_line_ranges(line_density_cols, threshold=0.35, min_run=max(2, w // 300)),
            gap=max(4, w // 200),
        )

        cleaned = gray.copy()
        if line_mask is not None:
            cleaned[line_mask > 0] = 255
        else:
            for s, e in hranges:
                cleaned[max(0, s - 1): min(h, e + 2), :] = 255
            for s, e in vranges:
                cleaned[:, max(0, s - 1): min(w, e + 2)] = 255

        # 基于横线切分大区块，再根据竖线进一步分列
        boundaries = [0]
        for s, e in hranges:
            mid = (s + e) // 2
            if 0 < mid < h:
                boundaries.append(mid)
        boundaries.append(h)
        boundaries = sorted(set(boundaries))

        regions: List[Tuple[int, int, int, int]] = []
        min_region_h = max(40, h // 25)
        min_region_w = max(60, w // 8)

        for top, bottom in zip(boundaries, boundaries[1:]):
            if bottom - top < min_region_h:
                continue

            row_vranges = [(s, e) for s, e in vranges if e - s >= 1]
            col_boundaries = [0]
            for s, e in row_vranges:
                mid = (s + e) // 2
                if 0 < mid < w:
                    col_boundaries.append(mid)
            col_boundaries.append(w)
            col_boundaries = sorted(set(col_boundaries))

            local_regions = []
            for left, right in zip(col_boundaries, col_boundaries[1:]):
                if right - left < min_region_w:
                    continue
                pad_x = max(2, w // 200)
                pad_y = max(2, h // 300)
                x1, y1 = max(0, left + pad_x), max(0, top + pad_y)
                x2, y2 = min(w, right - pad_x), min(h, bottom - pad_y)
                if x2 - x1 >= min_region_w and y2 - y1 >= min_region_h:
                    local_regions.append((x1, y1, x2, y2))

            if not local_regions:
                regions.append((0, top, w, bottom))
            else:
                regions.extend(local_regions)

        if not regions:
            regions = [(0, 0, w, h)]

        cleaned_img = Image.fromarray(cleaned).convert("L")
        return cleaned_img, regions[:40]
    except Exception:
        return None, []


def _ocr_regions(image: Image.Image, lang: str) -> str:
    cleaned, regions = _detect_table_lines_and_regions(image)
    if cleaned is None or not regions:
        return ""

    region_texts: List[str] = []
    for x1, y1, x2, y2 in sorted(regions, key=lambda r: (r[1], r[0])):
        try:
            crop = cleaned.crop((x1, y1, x2, y2))
            if _image_is_too_blank(crop):
                continue
            crop = _basic_denoise(_maybe_upscale(crop, min_side=900))
            txt = _ocr_single_image(crop, lang)
            if _text_score(txt) >= 8:
                region_texts.append(_normalize_text(txt))
        except Exception:
            continue

    # 去掉连续重复片段，避免分区重叠导致重复识别
    deduped: List[str] = []
    for txt in region_texts:
        if not txt:
            continue
        if deduped and (txt in deduped[-1] or deduped[-1] in txt):
            better = txt if _text_score(txt) > _text_score(deduped[-1]) else deduped[-1]
            deduped[-1] = better
        else:
            deduped.append(txt)
    return _safe_join_text(deduped)

# -------------------------
# PyMuPDF 文本层兜底
# -------------------------
def _extract_text_with_fitz(file_content: bytes) -> tuple[str, List[str]]:
    if fitz is None:
        return "", ["未安装 PyMuPDF"]

    errors: List[str] = []
    texts: List[str] = []
    try:
        doc = fitz.open(stream=file_content, filetype="pdf")
    except Exception as e:
        return "", [f"PyMuPDF 打开失败: {e}"]

    try:
        page_count = _safe_doc_page_count(doc)
        for i in range(page_count):
            try:
                if i < 0 or i >= page_count:
                    errors.append(f"第 {i + 1} 页索引越界，已跳过")
                    continue
                page = doc.load_page(i)
                txt = _normalize_text(page.get_text("text"))
                if txt:
                    texts.append(txt)
            except Exception as e:
                errors.append(f"第 {i + 1} 页 PyMuPDF 文本提取失败: {e}")
    finally:
        try:
            doc.close()
        except Exception:
            pass

    return _safe_join_text(texts), errors


# -------------------------
# PDF -> OCR
# -------------------------
def _safe_doc_page_count(doc) -> int:
    try:
        count = int(getattr(doc, "page_count", 0))
    except Exception as e:
        raise PDFReadError(f"无法读取 PDF 页数：{e}")
    if count <= 0:
        raise PDFReadError("PDF 中没有可 OCR 的页面")
    return count


def _render_page_to_image(doc, page_index: int) -> Image.Image:
    page_count = _safe_doc_page_count(doc)
    if page_index < 0 or page_index >= page_count:
        raise PDFReadError(f"第 {page_index + 1} 页索引越界，page_count={page_count}")

    try:
        page = doc.load_page(page_index)
    except Exception as e:
        raise PDFReadError(f"第 {page_index + 1} 页加载失败：{e}")

    try:
        # 更高清一点，提升 OCR 稳定性
        pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        img_bytes = pix.tobytes("png")
        image = Image.open(io.BytesIO(img_bytes))
        image.load()
        return image.convert("RGB")
    except Exception as e:
        raise PDFReadError(f"第 {page_index + 1} 页渲染失败：{e}")


def _ocr_pdf_bytes(file_content: bytes) -> str:
    """对扫描版 PDF 做 OCR，并带自动纠偏/图像增强/页眉页脚去噪/表格分区。"""
    if fitz is None:
        raise PDFReadError("未安装 PyMuPDF，无法对扫描版 PDF 执行 OCR")
    if pytesseract is None:
        raise PDFReadError("未安装 pytesseract，无法对扫描版 PDF 执行 OCR")
    if Image is None:
        raise PDFReadError("未安装 Pillow，无法对扫描版 PDF 执行 OCR")
    if shutil.which("tesseract") is None:
        raise PDFReadError("系统未安装 tesseract，可执行 OCR 兜底失败")

    try:
        doc = fitz.open(stream=file_content, filetype="pdf")
    except Exception as e:
        raise PDFReadError(f"扫描版 PDF 打开失败：{e}")

    page_count = _safe_doc_page_count(doc)
    lang = _pick_ocr_languages()
    text_parts: List[str] = []
    page_errors: List[str] = []

    try:
        for i in range(page_count):
            try:
                image = _render_page_to_image(doc, i)
                normal_text = _ocr_page_image(image, lang)
                region_text = ""
                try:
                    region_text = _ocr_regions(image, lang)
                except Exception as sub_e:
                    page_errors.append(f"第 {i + 1} 页分区域 OCR 失败: {sub_e}")

                candidates = [t for t in (normal_text, region_text) if t]
                if candidates:
                    best = max(candidates, key=_text_score)
                    text_parts.append(best)
                else:
                    page_errors.append(f"第 {i + 1} 页 OCR 结果为空")
            except Exception as e:
                page_errors.append(f"第 {i + 1} 页 OCR 失败: {e}")
    finally:
        try:
            doc.close()
        except Exception:
            pass

    if text_parts:
        return _safe_join_text(text_parts)

    if page_errors:
        raise PDFReadError("OCR 未能提取到文本；" + "；".join(page_errors[:8]))

    raise PDFReadError("OCR 未能提取到文本，可能页面质量过低、严重模糊或页面为空白")


# -------------------------
# 对外接口
# -------------------------
def read_pdf(file_content: bytes) -> str:
    """从二进制内容读取 PDF，按 文本层 -> PyMuPDF 文本 -> OCR 顺序多级兜底。"""
    errors: List[str] = []

    # 第 1 层：pypdf 文本层
    try:
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file, strict=False)

        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as e:
                raise PDFReadError(f"PDF 已加密，无法直接读取：{e}")

        text, page_errors = _safe_extract_text_from_reader(reader)
        if text:
            return text
        errors.extend(page_errors[:5])
    except IndexError as e:
        errors.append(f"pypdf 索引越界: {e}")
    except PDFReadError as e:
        errors.append(str(e))
    except Exception as e:
        errors.append(f"pypdf 提取失败: {e}")

    # 第 2 层：PyMuPDF 文本层兜底
    try:
        fitz_text, fitz_errors = _extract_text_with_fitz(file_content)
        if fitz_text:
            return fitz_text
        errors.extend(fitz_errors[:5])
    except Exception as e:
        errors.append(f"PyMuPDF 文本层兜底失败: {e}")

    # 第 3 层：OCR 兜底
    try:
        ocr_text = _ocr_pdf_bytes(file_content)
        if ocr_text:
            return ocr_text
    except Exception as e:
        errors.append(f"OCR 兜底失败: {e}")

    joined = "；".join([x for x in errors if x][:8])
    if joined:
        raise PDFReadError(f"PDF 读取失败：{joined}")
    raise PDFReadError("PDF 读取失败：未提取到文本")


def read_pdf_from_path(file_path: str) -> str:
    """从文件路径读取 PDF。"""
    try:
        with open(file_path, "rb") as f:
            return read_pdf(f.read())
    except PDFReadError:
        raise
    except Exception as e:
        raise PDFReadError(f"PDF 读取失败: {e}")
