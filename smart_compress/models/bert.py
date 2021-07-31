from argparse import ArgumentParser
from datetime import datetime

import datasets
import torch
from smart_compress.models.base import BaseModule
from transformers.models.bert import BertConfig, BertForSequenceClassification


class BertModule(BaseModule):
    @staticmethod
    def add_argparse_args(parent_parser):
        parser = ArgumentParser(
            parents=[BaseModule.add_argparse_args(parent_parser)], add_help=False
        )
        parser.add_argument("--num_labels", default=2, type=int)
        parser.add_argument(
            "--pretrained_model_name", default="bert-base-uncased", type=str
        )
        parser.add_argument("--freeze", action="store_true", dest="freeze")
        parser.add_argument(
            "--no_pretrained", action="store_false", dest="use_pretrained"
        )
        return parser

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.save_hyperparameters()

        if self.hparams.use_pretrained:
            self.model = BertForSequenceClassification.from_pretrained(
                self.hparams.pretrained_model_name, num_labels=self.hparams.num_labels
            )

            if self.hparams.freeze:
                for param in self.model.bert.parameters():
                    param.requires_grad = False
        else:
            self.model = BertForSequenceClassification(
                BertConfig.from_pretrained(
                    self.hparams.pretrained_model_name,
                    num_labels=self.hparams.num_labels,
                )
            )

        self.metric = datasets.load_metric(
            "glue",
            self.hparams.task_name,
            experiment_id=datetime.now().strftime("%d-%m-%Y_%H-%M-%S"),
        )

    def calculate_loss(self, batch):
        inputs, labels = batch

        outputs = self(inputs, labels)
        loss = outputs.loss

        return labels, loss, outputs

    def accuracy_function(self, outputs: torch.Tensor, ground_truth: torch.Tensor):
        if outputs.logits.dtype == torch.float:
            preds = outputs.logits.view(-1)
        else:
            preds = torch.argmax(outputs.logits, axis=1)

        return self.metric.compute(
            predictions=preds.detach().cpu().numpy(),
            references=ground_truth.detach().cpu().numpy(),
        )

    def forward(self, x, labels):
        return self.model(**x, labels=labels)
