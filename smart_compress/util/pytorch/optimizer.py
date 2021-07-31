from torch.optim import SGD, Adam, Optimizer
from torch.optim.adamw import AdamW

__all__ = ["OptimLP"]


class OptimLP(Optimizer):
    """
    A low-precision optimizer wrapper that handles weight, gradient, accumulator quantization.

    Args:
        - :attr: `optim`: underlying optimizer to use
        - :attr: `weight_quant`: a weight quantization function which takes a pytorch tensor and returns a tensor. If None, does not quantize weight.
        - :attr: `grad_quant`: a gradient quantization function which takes a pytorch tensor and returns a tensor. If None, does not quantize weight.
        - :attr: `grad_scaling`: float, scaling factor before apply gradient quantization.
        - :attr: `momentum_quant`: a momentum quantization function which takes a pytorch tensor and returns a tensor.
                                   If None, does not quantize weight.
        - :attr: `acc_quant`: a accumulator quantization function which takes
                              a pytorch tensor and returns a tensor. If not None, a
                              OptimLP object would create memory copies of model parameters that serve as
                              gradient accumulators. If None, does not use gradient accumulators.

    Example:
        >>> weight_q = quantizer(...) # define weight quantization
        >>> optimizer = SGD(model.parameters(), lr=0.1, momentum=0.9)
        >>> optimizer = OptimLP(optiimizer, weight_quant=weight_q)
    """

    def __init__(
        self,
        optim,
        weight_quant=None,
        grad_scaling=1.0,
        grad_quant=None,
        momentum_quant=None,
        acc_quant=None,
    ):
        super().__init__(optim.param_groups, optim.defaults)  # place holder

        # python dictionary does not copy by default
        self.param_groups = optim.param_groups
        self.optim = optim

        assert grad_scaling > 0, "gradient scaling must be positive"
        self.grad_scaling = grad_scaling

        self.weight_quant = weight_quant
        self.grad_quant = grad_quant
        self.momentum_quant = momentum_quant
        self.acc_quant = acc_quant

        if isinstance(self.optim, SGD):
            self.momentum_keys = [("momentum_buffer", dict())]
        elif isinstance(self.optim, Adam) or isinstance(self.optim, AdamW):
            # TODO: support amsgrad
            self.momentum_keys = [
                ("exp_avg", dict()),
                ("exp_avg_sq", dict(all_positive=True)),
            ]
        else:
            raise NotImplementedError("Only supporting Adam and SGD for now. ")

        if self.acc_quant != None:
            self.weight_acc = {}
            for group in self.param_groups:
                for p in group["params"]:
                    self.weight_acc[p] = p.detach().clone().type_as(p)

    def _pre_closure(self):
        # quantize gradient
        if not self.grad_quant is None:
            for group in self.param_groups:
                if "no_grad_compression" in group and group["no_grad_compression"]:
                    continue

                for p in group["params"]:
                    if not p.requires_grad or p.grad is None:
                        continue
                    p.grad.data = self.grad_quant(p.grad.data * self.grad_scaling).data

        # switch acc into weight before stepping
        if not self.acc_quant is None:
            for group in self.param_groups:
                for p in group["params"]:
                    p.data = self.weight_acc[p].data

    def _post_closure(self):
        # quantize gradient
        if not self.grad_quant is None:
            for group in self.param_groups:
                if "no_grad_compression" in group and group["no_grad_compression"]:
                    continue

                for p in group["params"]:
                    if not p.requires_grad or p.grad is None:
                        continue
                    p.grad.data = self.grad_quant(p.grad.data * self.grad_scaling).data

        # quantize weight from acc
        if not self.weight_quant is None:
            for group in self.param_groups:
                if "no_weight_compression" in group and group["no_weight_compression"]:
                    continue

                for p in group["params"]:
                    p.data = self.weight_quant(p.data).data

        # quantize momentum
        if not self.momentum_quant is None:
            for group in self.param_groups:
                if (
                    "no_momentum_compression" in group
                    and group["no_momentum_compression"]
                ):
                    continue

                if isinstance(self.optim, SGD) and group["momentum"] == 0:
                    continue
                for p in group["params"]:
                    if not p.requires_grad or p.grad is None:
                        continue

                    param_state = self.optim.state[p]
                    for key, kwargs in self.momentum_keys:
                        param_state[key].data = self.momentum_quant(
                            param_state[key], **kwargs
                        ).data

    def step(self, closure=None):
        """
        Performs one step of optimization with the underlying optimizer.
        Quantizes gradient and momentum before stepping. Quantizes gradient accumulator and weight after stepping.
        """

        def closure_(*args, **kwargs):
            value = closure(*args, **kwargs)
            self._pre_closure()
            return value

        loss = self.optim.step(closure=closure_)
        self._post_closure()

        return loss

    def __repr__(self):
        return "LP Optimizer: {}".format(self.optim.__repr__())

    def __str__(self):
        return "LP Optimizer: {}".format(self.optim.__str__())
