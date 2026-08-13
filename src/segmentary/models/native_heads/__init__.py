"""Native dense segmentation heads."""

from .aspp import ASPPHead
from .deeplabv3plus import DeepLabV3PlusHead
from .dpt import DPTHead
from .fcn import FCNHead
from .lraspp import LRASPPHead
from .ocr import OCRHead
from .psp import PSPHead
from .segformer import SegFormerMLPHead
from .uper import UPerHead

__all__ = [
    "ASPPHead",
    "DPTHead",
    "DeepLabV3PlusHead",
    "FCNHead",
    "LRASPPHead",
    "OCRHead",
    "PSPHead",
    "SegFormerMLPHead",
    "UPerHead",
]
