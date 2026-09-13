# Copyright retained from upstream; Apache-2.0. See LICENSE and PROVENANCE.md.
# Modified by Segmentary: local imports and unused legacy code removal.
# ruff: noqa
# 3D version of TransUNet; Copyright Johns Hopkins University
# Modified from nnUNet


import torch
import numpy as np
import torch.nn.functional
import torch.nn.functional as F

from copy import deepcopy
from torch import nn
from torch.cuda.amp import autocast
from scipy.optimize import linear_sum_assignment


from .vit_modeling import Transformer
from .vit_modeling import CONFIGS as CONFIGS_ViT

softmax_helper = lambda x: F.softmax(x, 1)


class InitWeights_He(object):
    def __init__(self, neg_slope=1e-2):
        self.neg_slope = neg_slope

    def __call__(self, module):
        if (
            isinstance(module, nn.Conv3d)
            or isinstance(module, nn.Conv2d)
            or isinstance(module, nn.ConvTranspose2d)
            or isinstance(module, nn.ConvTranspose3d)
        ):
            module.weight = nn.init.kaiming_normal_(module.weight, a=self.neg_slope)
            if module.bias is not None:
                module.bias = nn.init.constant_(module.bias, 0)


class ConvDropoutNormNonlin(nn.Module):
    """
    fixes a bug in ConvDropoutNormNonlin where lrelu was used regardless of nonlin. Bad.
    """

    def __init__(
        self,
        input_channels,
        output_channels,
        conv_op=nn.Conv2d,
        conv_kwargs=None,
        norm_op=nn.BatchNorm2d,
        norm_op_kwargs=None,
        dropout_op=nn.Dropout2d,
        dropout_op_kwargs=None,
        nonlin=nn.LeakyReLU,
        nonlin_kwargs=None,
    ):
        super(ConvDropoutNormNonlin, self).__init__()
        if nonlin_kwargs is None:
            nonlin_kwargs = {"negative_slope": 1e-2, "inplace": True}
        if dropout_op_kwargs is None:
            dropout_op_kwargs = {"p": 0.5, "inplace": True}
        if norm_op_kwargs is None:
            norm_op_kwargs = {"eps": 1e-5, "affine": True, "momentum": 0.1}
        if conv_kwargs is None:
            conv_kwargs = {"kernel_size": 3, "stride": 1, "padding": 1, "dilation": 1, "bias": True}

        self.nonlin_kwargs = nonlin_kwargs
        self.nonlin = nonlin
        self.dropout_op = dropout_op
        self.dropout_op_kwargs = dropout_op_kwargs
        self.norm_op_kwargs = norm_op_kwargs
        self.conv_kwargs = conv_kwargs
        self.conv_op = conv_op
        self.norm_op = norm_op

        self.conv = self.conv_op(input_channels, output_channels, **self.conv_kwargs)
        if (
            self.dropout_op is not None
            and self.dropout_op_kwargs["p"] is not None
            and self.dropout_op_kwargs["p"] > 0
        ):
            self.dropout = self.dropout_op(**self.dropout_op_kwargs)
        else:
            self.dropout = None
        self.instnorm = self.norm_op(output_channels, **self.norm_op_kwargs)
        self.lrelu = self.nonlin(**self.nonlin_kwargs)

    def forward(self, x):
        x = self.conv(x)
        if self.dropout is not None:
            x = self.dropout(x)
        return self.lrelu(self.instnorm(x))


class ConvDropoutNonlinNorm(ConvDropoutNormNonlin):
    def forward(self, x):
        x = self.conv(x)
        if self.dropout is not None:
            x = self.dropout(x)
        return self.instnorm(self.lrelu(x))


class StackedConvLayers(nn.Module):
    def __init__(
        self,
        input_feature_channels,
        output_feature_channels,
        num_convs,
        conv_op=nn.Conv2d,
        conv_kwargs=None,
        norm_op=nn.BatchNorm2d,
        norm_op_kwargs=None,
        dropout_op=nn.Dropout2d,
        dropout_op_kwargs=None,
        nonlin=nn.LeakyReLU,
        nonlin_kwargs=None,
        first_stride=None,
        basic_block=ConvDropoutNormNonlin,
    ):
        """
        stacks ConvDropoutNormLReLU layers. initial_stride will only be applied to first layer in the stack. The other parameters affect all layers
        :param input_feature_channels:
        :param output_feature_channels:
        :param num_convs:
        :param dilation:
        :param kernel_size:
        :param padding:
        :param dropout:
        :param initial_stride:
        :param conv_op:
        :param norm_op:
        :param dropout_op:
        :param inplace:
        :param neg_slope:
        :param norm_affine:
        :param conv_bias:
        """
        self.input_channels = input_feature_channels
        self.output_channels = output_feature_channels

        if nonlin_kwargs is None:
            nonlin_kwargs = {"negative_slope": 1e-2, "inplace": True}
        if dropout_op_kwargs is None:
            dropout_op_kwargs = {"p": 0.5, "inplace": True}
        if norm_op_kwargs is None:
            norm_op_kwargs = {"eps": 1e-5, "affine": True, "momentum": 0.1}
        if conv_kwargs is None:
            conv_kwargs = {"kernel_size": 3, "stride": 1, "padding": 1, "dilation": 1, "bias": True}

        self.nonlin_kwargs = nonlin_kwargs
        self.nonlin = nonlin
        self.dropout_op = dropout_op
        self.dropout_op_kwargs = dropout_op_kwargs
        self.norm_op_kwargs = norm_op_kwargs
        self.conv_kwargs = conv_kwargs
        self.conv_op = conv_op
        self.norm_op = norm_op

        if first_stride is not None:
            self.conv_kwargs_first_conv = deepcopy(conv_kwargs)
            self.conv_kwargs_first_conv["stride"] = first_stride
        else:
            self.conv_kwargs_first_conv = conv_kwargs

        super(StackedConvLayers, self).__init__()
        self.blocks = nn.Sequential(
            *(
                [
                    basic_block(
                        input_feature_channels,
                        output_feature_channels,
                        self.conv_op,
                        self.conv_kwargs_first_conv,
                        self.norm_op,
                        self.norm_op_kwargs,
                        self.dropout_op,
                        self.dropout_op_kwargs,
                        self.nonlin,
                        self.nonlin_kwargs,
                    )
                ]
                + [
                    basic_block(
                        output_feature_channels,
                        output_feature_channels,
                        self.conv_op,
                        self.conv_kwargs,
                        self.norm_op,
                        self.norm_op_kwargs,
                        self.dropout_op,
                        self.dropout_op_kwargs,
                        self.nonlin,
                        self.nonlin_kwargs,
                    )
                    for _ in range(num_convs - 1)
                ]
            )
        )

    def forward(self, x):
        return self.blocks(x)


def print_module_training_status(module):
    if (
        isinstance(module, nn.Conv2d)
        or isinstance(module, nn.Conv3d)
        or isinstance(module, nn.Dropout3d)
        or isinstance(module, nn.Dropout2d)
        or isinstance(module, nn.Dropout)
        or isinstance(module, nn.InstanceNorm3d)
        or isinstance(module, nn.InstanceNorm2d)
        or isinstance(module, nn.InstanceNorm1d)
        or isinstance(module, nn.BatchNorm2d)
        or isinstance(module, nn.BatchNorm3d)
        or isinstance(module, nn.BatchNorm1d)
    ):
        print(str(module), module.training)


class Upsample(nn.Module):
    def __init__(self, size=None, scale_factor=None, mode="nearest", align_corners=False):
        super(Upsample, self).__init__()
        self.align_corners = align_corners
        self.mode = mode
        self.scale_factor = scale_factor
        self.size = size

    def forward(self, x):
        return nn.functional.interpolate(
            x,
            size=self.size,
            scale_factor=self.scale_factor,
            mode=self.mode,
            align_corners=self.align_corners,
        )


def c2_xavier_fill(module: nn.Module) -> None:
    """
    Initialize `module.weight` using the "XavierFill" implemented in Caffe2.
    Also initializes `module.bias` to 0.
    Args:
        module (torch.nn.Module): module to initialize.
    """
    # Caffe2 implementation of XavierFill in fact
    # corresponds to kaiming_uniform_ in PyTorch
    assert isinstance(module.weight, torch.Tensor)
    nn.init.kaiming_uniform_(module.weight, a=1)
    if module.bias is not None:
        # pyre-fixme[6]: Expected `Tensor` for 1st param but got `Union[nn.Module,
        #  torch.Tensor]`.
        assert isinstance(module.bias, torch.Tensor)
        nn.init.constant_(module.bias, 0)


class Generic_TransUNet_max_ppbp(nn.Module):
    DEFAULT_BATCH_SIZE_3D = 2
    DEFAULT_PATCH_SIZE_3D = (64, 192, 160)
    SPACING_FACTOR_BETWEEN_STAGES = 2
    BASE_NUM_FEATURES_3D = 30
    MAX_NUMPOOL_3D = 999
    MAX_NUM_FILTERS_3D = 320

    DEFAULT_PATCH_SIZE_2D = (256, 256)
    BASE_NUM_FEATURES_2D = 30
    DEFAULT_BATCH_SIZE_2D = 50
    MAX_NUMPOOL_2D = 999
    MAX_FILTERS_2D = 480

    use_this_for_batch_size_computation_2D = 19739648
    use_this_for_batch_size_computation_3D = 520000000  # 505789440

    def __init__(
        self,
        input_channels,
        base_num_features,
        num_classes,
        num_pool,
        num_conv_per_stage=2,
        feat_map_mul_on_downscale=2,
        conv_op=nn.Conv2d,
        norm_op=nn.BatchNorm2d,
        norm_op_kwargs=None,
        dropout_op=nn.Dropout2d,
        dropout_op_kwargs=None,
        nonlin=nn.LeakyReLU,
        nonlin_kwargs=None,
        deep_supervision=True,
        dropout_in_localization=False,
        final_nonlin=softmax_helper,
        weightInitializer=InitWeights_He(1e-2),
        pool_op_kernel_sizes=None,
        conv_kernel_sizes=None,
        upscale_logits=False,
        convolutional_pooling=False,
        convolutional_upsampling=False,  # TODO default False
        max_num_features=None,
        basic_block=ConvDropoutNormNonlin,
        seg_output_use_bias=False,
        patch_size=None,
        is_vit_pretrain=False,
        vit_depth=12,
        vit_hidden_size=768,
        vit_mlp_dim=3072,
        vit_num_heads=12,
        max_msda="",
        is_max_ms=True,
        is_max_ms_fpn=False,
        max_n_fpn=4,
        max_ms_idxs=[-4, -3, -2],
        max_ss_idx=0,
        is_max_bottleneck_transformer=False,
        max_seg_weight=1.0,
        max_hidden_dim=256,
        max_dec_layers=10,
        mw=0.5,
        is_max=True,
        is_masked_attn=False,
        is_max_ds=False,
        is_masking=False,
        is_masking_argmax=False,
        is_fam=False,
        fam_k=5,
        fam_reduct_ratio=8,
        is_max_hungarian=False,
        num_queries=None,
        is_max_cls=False,
        point_rend=False,
        num_point_rend=None,
        no_object_weight=None,
        is_mhsa_float32=False,
        no_max_hw_pe=False,
        max_infer=None,
        cost_weight=[2.0, 5.0, 5.0],
        vit_layer_scale=False,
        decoder_layer_scale=False,
    ):

        super(Generic_TransUNet_max_ppbp, self).__init__()

        # newly added
        self.is_fam = is_fam
        (
            self.is_max,
            self.max_msda,
            self.is_max_ms,
            self.is_max_ms_fpn,
            self.max_n_fpn,
            self.max_ss_idx,
            self.mw,
        ) = is_max, max_msda, is_max_ms, is_max_ms_fpn, max_n_fpn, max_ss_idx, mw
        self.max_ms_idxs = max_ms_idxs

        self.is_max_cls = is_max_cls
        self.is_masked_attn, self.is_max_ds = is_masked_attn, is_max_ds
        self.is_max_bottleneck_transformer = is_max_bottleneck_transformer

        self.convolutional_upsampling = convolutional_upsampling
        self.convolutional_pooling = convolutional_pooling
        self.upscale_logits = upscale_logits
        if nonlin_kwargs is None:
            nonlin_kwargs = {"negative_slope": 1e-2, "inplace": True}
        if dropout_op_kwargs is None:
            dropout_op_kwargs = {"p": 0.5, "inplace": True}
        if norm_op_kwargs is None:
            norm_op_kwargs = {"eps": 1e-5, "affine": True, "momentum": 0.1}

        self.conv_kwargs = {"stride": 1, "dilation": 1, "bias": True}

        self.nonlin = nonlin
        self.nonlin_kwargs = nonlin_kwargs
        self.dropout_op_kwargs = dropout_op_kwargs
        self.norm_op_kwargs = norm_op_kwargs
        self.weightInitializer = weightInitializer
        self.conv_op = conv_op
        self.norm_op = norm_op
        self.dropout_op = dropout_op
        self.num_classes = num_classes
        self.final_nonlin = final_nonlin
        self._deep_supervision = deep_supervision
        self.do_ds = deep_supervision

        if conv_op == nn.Conv2d:
            upsample_mode = "bilinear"
            pool_op = nn.MaxPool2d
            transpconv = nn.ConvTranspose2d
            if pool_op_kernel_sizes is None:
                pool_op_kernel_sizes = [(2, 2)] * num_pool
            if conv_kernel_sizes is None:
                conv_kernel_sizes = [(3, 3)] * (num_pool + 1)
        elif conv_op == nn.Conv3d:
            upsample_mode = "trilinear"
            pool_op = nn.MaxPool3d
            transpconv = nn.ConvTranspose3d
            if pool_op_kernel_sizes is None:
                pool_op_kernel_sizes = [(2, 2, 2)] * num_pool
            if conv_kernel_sizes is None:
                conv_kernel_sizes = [(3, 3, 3)] * (num_pool + 1)
        else:
            raise ValueError("unknown convolution dimensionality, conv op: %s" % str(conv_op))

        self.input_shape_must_be_divisible_by = np.prod(pool_op_kernel_sizes, 0, dtype=np.int64)
        self.pool_op_kernel_sizes = pool_op_kernel_sizes
        self.conv_kernel_sizes = conv_kernel_sizes

        self.conv_pad_sizes = []
        for krnl in self.conv_kernel_sizes:
            self.conv_pad_sizes.append([1 if i == 3 else 0 for i in krnl])

        if max_num_features is None:
            if self.conv_op == nn.Conv3d:
                self.max_num_features = self.MAX_NUM_FILTERS_3D
            else:
                self.max_num_features = self.MAX_FILTERS_2D
        else:
            self.max_num_features = max_num_features

        self.conv_blocks_context = []
        self.conv_blocks_localization = []
        self.td = []
        self.tu = []

        self.fams = []

        output_features = base_num_features
        input_features = input_channels

        for d in range(num_pool):
            # determine the first stride
            if d != 0 and self.convolutional_pooling:
                first_stride = pool_op_kernel_sizes[d - 1]
            else:
                first_stride = None

            self.conv_kwargs["kernel_size"] = self.conv_kernel_sizes[d]
            self.conv_kwargs["padding"] = self.conv_pad_sizes[d]
            # add convolutions
            self.conv_blocks_context.append(
                StackedConvLayers(
                    input_features,
                    output_features,
                    num_conv_per_stage,
                    self.conv_op,
                    self.conv_kwargs,
                    self.norm_op,
                    self.norm_op_kwargs,
                    self.dropout_op,
                    self.dropout_op_kwargs,
                    self.nonlin,
                    self.nonlin_kwargs,
                    first_stride,
                    basic_block=basic_block,
                )
            )
            if not self.convolutional_pooling:
                self.td.append(pool_op(pool_op_kernel_sizes[d]))
            input_features = output_features
            output_features = int(np.round(output_features * feat_map_mul_on_downscale))

            output_features = min(output_features, self.max_num_features)

        # now the bottleneck.
        # determine the first stride
        if self.convolutional_pooling:
            first_stride = pool_op_kernel_sizes[-1]
        else:
            first_stride = None

        # the output of the last conv must match the number of features from the skip connection if we are not using
        # convolutional upsampling. If we use convolutional upsampling then the reduction in feature maps will be
        # done by the transposed conv
        if self.convolutional_upsampling:
            final_num_features = output_features
        else:
            final_num_features = self.conv_blocks_context[-1].output_channels

        self.conv_kwargs["kernel_size"] = self.conv_kernel_sizes[num_pool]
        self.conv_kwargs["padding"] = self.conv_pad_sizes[num_pool]
        self.conv_blocks_context.append(
            nn.Sequential(
                StackedConvLayers(
                    input_features,
                    output_features,
                    num_conv_per_stage - 1,
                    self.conv_op,
                    self.conv_kwargs,
                    self.norm_op,
                    self.norm_op_kwargs,
                    self.dropout_op,
                    self.dropout_op_kwargs,
                    self.nonlin,
                    self.nonlin_kwargs,
                    first_stride,
                    basic_block=basic_block,
                ),
                StackedConvLayers(
                    output_features,
                    final_num_features,
                    1,
                    self.conv_op,
                    self.conv_kwargs,
                    self.norm_op,
                    self.norm_op_kwargs,
                    self.dropout_op,
                    self.dropout_op_kwargs,
                    self.nonlin,
                    self.nonlin_kwargs,
                    basic_block=basic_block,
                ),
            )
        )

        # if we don't want to do dropout in the localization pathway then we set the dropout prob to zero here
        if not dropout_in_localization:
            old_dropout_p = self.dropout_op_kwargs["p"]
            self.dropout_op_kwargs["p"] = 0.0

        # now lets build the localization pathway
        for u in range(num_pool):
            nfeatures_from_down = final_num_features
            nfeatures_from_skip = self.conv_blocks_context[
                -(2 + u)
            ].output_channels  # self.conv_blocks_context[-1] is bottleneck, so start with -2
            n_features_after_tu_and_concat = nfeatures_from_skip * 2

            # the first conv reduces the number of features to match those of skip
            # the following convs work on that number of features
            # if not convolutional upsampling then the final conv reduces the num of features again
            if u != num_pool - 1 and not self.convolutional_upsampling:
                final_num_features = self.conv_blocks_context[-(3 + u)].output_channels
            else:
                final_num_features = nfeatures_from_skip

            if not self.convolutional_upsampling:
                self.tu.append(
                    Upsample(scale_factor=pool_op_kernel_sizes[-(u + 1)], mode=upsample_mode)
                )
            else:
                self.tu.append(
                    transpconv(
                        nfeatures_from_down,
                        nfeatures_from_skip,
                        pool_op_kernel_sizes[-(u + 1)],
                        pool_op_kernel_sizes[-(u + 1)],
                        bias=False,
                    )
                )

            self.conv_kwargs["kernel_size"] = self.conv_kernel_sizes[-(u + 1)]
            self.conv_kwargs["padding"] = self.conv_pad_sizes[-(u + 1)]
            self.conv_blocks_localization.append(
                nn.Sequential(
                    StackedConvLayers(
                        n_features_after_tu_and_concat,
                        nfeatures_from_skip,
                        num_conv_per_stage - 1,
                        self.conv_op,
                        self.conv_kwargs,
                        self.norm_op,
                        self.norm_op_kwargs,
                        self.dropout_op,
                        self.dropout_op_kwargs,
                        self.nonlin,
                        self.nonlin_kwargs,
                        basic_block=basic_block,
                    ),
                    StackedConvLayers(
                        nfeatures_from_skip,
                        final_num_features,
                        1,
                        self.conv_op,
                        self.conv_kwargs,
                        self.norm_op,
                        self.norm_op_kwargs,
                        self.dropout_op,
                        self.dropout_op_kwargs,
                        self.nonlin,
                        self.nonlin_kwargs,
                        basic_block=basic_block,
                    ),
                )
            )

        if self.is_fam:
            self.fams = nn.ModuleList(self.fams)

        if self.do_ds:
            self.seg_outputs = []
            for ds in range(len(self.conv_blocks_localization)):
                self.seg_outputs.append(
                    conv_op(
                        self.conv_blocks_localization[ds][-1].output_channels,
                        num_classes,
                        1,
                        1,
                        0,
                        1,
                        1,
                        seg_output_use_bias,
                    )
                )
            self.seg_outputs = nn.ModuleList(self.seg_outputs)

        self.upscale_logits_ops = []
        cum_upsample = np.cumprod(np.vstack(pool_op_kernel_sizes), axis=0)[::-1]
        for usl in range(num_pool - 1):
            if self.upscale_logits:
                self.upscale_logits_ops.append(
                    Upsample(
                        scale_factor=tuple([int(i) for i in cum_upsample[usl + 1]]),
                        mode=upsample_mode,
                    )
                )
            else:
                self.upscale_logits_ops.append(lambda x: x)

        if not dropout_in_localization:
            self.dropout_op_kwargs["p"] = old_dropout_p

        # register all modules properly
        self.conv_blocks_localization = nn.ModuleList(self.conv_blocks_localization)
        self.conv_blocks_context = nn.ModuleList(self.conv_blocks_context)
        self.td = nn.ModuleList(self.td)
        self.tu = nn.ModuleList(self.tu)

        if self.upscale_logits:
            self.upscale_logits_ops = nn.ModuleList(
                self.upscale_logits_ops
            )  # lambda x:x is not a Module so we need to distinguish here

        if self.weightInitializer is not None:
            self.apply(self.weightInitializer)
            # self.apply(print_module_training_status)

        # Transformer configuration
        if self.is_max_bottleneck_transformer:
            self.patch_size = patch_size  # e.g. [48, 192, 192]
            config_vit = deepcopy(CONFIGS_ViT["R50-ViT-B_16"])
            config_vit.transformer.num_layers = vit_depth
            config_vit.hidden_size = vit_hidden_size  # 768
            config_vit.transformer.mlp_dim = vit_mlp_dim  # 3072
            config_vit.transformer.num_heads = vit_num_heads  # 12
            self.conv_more = nn.Conv3d(config_vit.hidden_size, output_features, 1)
            num_pool_per_axis = np.prod(np.array(pool_op_kernel_sizes), axis=0)
            num_pool_per_axis = np.log2(num_pool_per_axis).astype(np.uint8)
            feat_size = [
                int(self.patch_size[0] / 2 ** num_pool_per_axis[0]),
                int(self.patch_size[1] / 2 ** num_pool_per_axis[1]),
                int(self.patch_size[2] / 2 ** num_pool_per_axis[2]),
            ]
            self.transformer = Transformer(
                config_vit,
                feat_size=feat_size,
                vis=False,
                feat_channels=output_features,
                use_layer_scale=vit_layer_scale,
            )
            if is_vit_pretrain:
                raise ValueError("Segmentary permits only random initialization")

        if self.is_max:
            raise ValueError("This vendored variant is the 3D TransUNet encoder model")

    def forward(self, x):
        skips = []
        seg_outputs = []
        for d in range(len(self.conv_blocks_context) - 1):
            x = self.conv_blocks_context[d](x)
            skips.append(x)
            if not self.convolutional_pooling:
                x = self.td[d](x)

        x = self.conv_blocks_context[-1](x)
        ######### TransUNet #########
        if self.is_max_bottleneck_transformer:
            x, attn = self.transformer(x)  # [b, hidden, d/8, h/16, w/16]
            x = self.conv_more(x)
        #############################

        ds_feats = []  # obtain multi-scale feature
        ds_feats.append(x)
        for u in range(len(self.tu)):
            if (
                u < len(self.tu) - 1
                and isinstance(self.is_fam, str)
                and self.is_fam.startswith("fam_down")
            ):
                skip_down = (
                    nn.Upsample(size=x.shape[2:])(skips[-(u + 1)])
                    if x.shape[2:] != skips[-(u + 1)].shape[2:]
                    else skips[-(u + 1)]
                )
                x_align = self.fams[u](x, x_l=skip_down)
                x = x + x_align

            x = self.tu[u](x)  # merely an upsampling or transposeconv operation

            if isinstance(self.is_fam, bool) and self.is_fam:
                x_align = self.fams[u](x, x_l=skips[-(u + 1)])
                x = x + x_align
            x = torch.cat((x, skips[-(u + 1)]), dim=1)
            x = self.conv_blocks_localization[u](x)
            if self.do_ds:
                seg_outputs.append(self.final_nonlin(self.seg_outputs[u](x)))
            ds_feats.append(x)

        ######### Max PPB+ #########
        if self.is_max:
            if self.is_max_ms:  # is_max_ms_fpn
                multi_scale_features = []
                ms_pixel_feats = (
                    ds_feats[: self.max_n_fpn]
                    if self.is_max_ms_fpn
                    else [ds_feats[i] for i in self.max_ms_idxs]
                )

                for idx, f in enumerate(ms_pixel_feats):
                    f = self.input_proj[
                        idx
                    ](
                        f
                    )  # proj into same spatial/channel dim , but transformer_decoder also project to same mask_dim
                    multi_scale_features.append(f)
                transformer_decoder_in_feature = (
                    self.linear_encoder_feature(torch.cat(multi_scale_features, dim=1))
                    if self.is_max_ms_fpn
                    else multi_scale_features
                )  # feature pyramid
                mask_features = self.linear_mask_features(ds_feats[-1])  # following SingleScale
            else:
                transformer_decoder_in_feature = self.linear_encoder_feature(
                    ds_feats[self.max_ss_idx]
                )
                mask_features = self.linear_mask_features(ds_feats[-1])

            predictions = self.predictor(transformer_decoder_in_feature, mask_features, mask=None)

            if self.is_max_cls and self.is_max_ds:
                if self._deep_supervision and self.do_ds:
                    return [predictions] + [
                        i(j)
                        for i, j in zip(list(self.upscale_logits_ops)[::-1], seg_outputs[:-1][::-1])
                    ]
                return predictions

            elif (
                self.is_max_ds and not self.is_max_ms and self.mw == 1.0
            ):  # aux output of max decoder
                aux_out = [p["pred_masks"] for p in predictions["aux_outputs"]]  # ascending order
                all_out = [predictions["pred_masks"]] + aux_out[
                    ::-1
                ]  # reverse order, w/o sigmoid activation
                return tuple(all_out)
            elif not self.is_max_ds and self.mw == 1.0:
                raise NotImplementedError
            else:
                raise NotImplementedError

        #############################

        if self._deep_supervision and self.do_ds:  # assuming turn off ds
            return tuple(
                [seg_outputs[-1]]
                + [
                    i(j)
                    for i, j in zip(list(self.upscale_logits_ops)[::-1], seg_outputs[:-1][::-1])
                ]
            )
        else:
            return seg_outputs[-1]

    @staticmethod
    def compute_approx_vram_consumption(
        patch_size,
        num_pool_per_axis,
        base_num_features,
        max_num_features,
        num_modalities,
        num_classes,
        pool_op_kernel_sizes,
        deep_supervision=False,
        conv_per_stage=2,
    ):
        """
        This only applies for num_conv_per_stage and convolutional_upsampling=True
        not real vram consumption. just a constant term to which the vram consumption will be approx proportional
        (+ offset for parameter storage)
        :param deep_supervision:
        :param patch_size:
        :param num_pool_per_axis:
        :param base_num_features:
        :param max_num_features:
        :param num_modalities:
        :param num_classes:
        :param pool_op_kernel_sizes:
        :return:
        """
        if not isinstance(num_pool_per_axis, np.ndarray):
            num_pool_per_axis = np.array(num_pool_per_axis)

        npool = len(pool_op_kernel_sizes)

        map_size = np.array(patch_size)
        tmp = np.int64(
            (conv_per_stage * 2 + 1) * np.prod(map_size, dtype=np.int64) * base_num_features
            + num_modalities * np.prod(map_size, dtype=np.int64)
            + num_classes * np.prod(map_size, dtype=np.int64)
        )

        num_feat = base_num_features

        for p in range(npool):
            for pi in range(len(num_pool_per_axis)):
                map_size[pi] /= pool_op_kernel_sizes[p][pi]
            num_feat = min(num_feat * 2, max_num_features)
            num_blocks = (
                (conv_per_stage * 2 + 1) if p < (npool - 1) else conv_per_stage
            )  # conv_per_stage + conv_per_stage for the convs of encode/decode and 1 for transposed conv
            tmp += num_blocks * np.prod(map_size, dtype=np.int64) * num_feat
            if deep_supervision and p < (npool - 2):
                tmp += np.prod(map_size, dtype=np.int64) * num_classes
            # print(p, map_size, num_feat, tmp)
        return tmp


default_dict = {
    "base_num_features": 32,
    "conv_per_stage": 2,
    "initial_lr": 0.01,
    "lr_scheduler": None,
    "lr_scheduler_eps": 0.001,
    "lr_scheduler_patience": 30,
    "lr_threshold": 1e-06,
    "max_num_epochs": 1000,
    "net_conv_kernel_sizes": [[1, 3, 3], [3, 3, 3], [3, 3, 3], [3, 3, 3], [3, 3, 3], [3, 3, 3]],
    "net_num_pool_op_kernel_sizes": [[1, 2, 2], [2, 2, 2], [2, 2, 2], [2, 2, 2], [2, 2, 2]],
    "net_pool_per_axis": [4, 5, 5],
    "num_batches_per_epoch": 250,
    "num_classes": 17,
    "num_input_channels": 1,
    "transpose_backward": [0, 1, 2],
    "transpose_forward": [0, 1, 2],
}
