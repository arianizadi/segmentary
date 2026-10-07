"""Bound nnU-Net 2.8.1 trainer variants, imported only inside the backend interpreter.

nnU-Net 2.8.1 ships epoch-count variants but no SGD fine-tuning trainer with a
lower learning rate, so ``nnUNetTrainerFinetune`` keeps every recipe element of
``nnUNetTrainer`` (SGD, Nesterov, poly schedule, loss, sampling, augmentation)
and changes only its defaults: initial learning rate 1e-3 and 150 epochs of 250
updates. The backend may override both from the bound configuration before
``initialize()`` builds the optimizer. nnU-Net cannot find this class by name,
so the backend constructs it directly and initialises the predictor manually.
"""

from __future__ import annotations

import torch
from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer

FINETUNE_INITIAL_LR = 1e-3
FINETUNE_EPOCHS = 150


class nnUNetTrainerFinetune(nnUNetTrainer):
    def __init__(
        self,
        plans: dict,
        configuration: str,
        fold: int,
        dataset_json: dict,
        device: torch.device = torch.device("cuda"),
    ) -> None:
        super().__init__(plans, configuration, fold, dataset_json, device)
        self.initial_lr = FINETUNE_INITIAL_LR
        self.num_epochs = FINETUNE_EPOCHS
