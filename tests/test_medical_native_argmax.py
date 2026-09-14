"""Native class decisions remain exact without stacking whole volumes."""

import numpy as np
import pytest

from segmentary.medical.torch_geometry import native_argmax


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("strided", [False, True])
def test_argmax_matches_numpy_for_random_values_all_ties_and_strided_inputs(dtype, strided):
    arrays = np.random.default_rng(919).uniform(-1, 1, size=(3, 9, 11, 13)).astype(dtype)
    patterns = np.asarray(
        [
            [0, 0, 0],
            [1, 1, 0],
            [0, 1, 1],
            [1, 0, 1],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 0],
            [-0.0, 0.0, -0.0],
            [-1, -1, -1],
        ],
        dtype=dtype,
    )
    arrays[:, 0, 0, : len(patterns)] = patterns.T
    channels = [channel.transpose(2, 0, 1) if strided else channel for channel in arrays]
    before = [channel.copy() for channel in channels]
    for channel in channels:
        channel.flags.writeable = False
    actual = native_argmax(channels)
    assert actual.dtype == np.uint8
    np.testing.assert_array_equal(actual, np.stack(channels).argmax(0).astype(np.uint8))
    assert set(np.unique(actual)) == {0, 1, 2}
    for previous, channel in zip(before, channels, strict=True):
        np.testing.assert_array_equal(previous, channel)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_argmax_rejects_nonfinite_channels(value):
    channels = [np.zeros((2, 3, 4), np.float32) for _ in range(3)]
    channels[1][0, 0, 0] = value
    with pytest.raises(ValueError, match="finite"):
        native_argmax(channels)


@pytest.mark.parametrize("invalid", ["count", "shape", "dimensions", "empty", "integer"])
def test_argmax_rejects_invalid_native_channel_contract(invalid):
    channels = [np.zeros((2, 3, 4), np.float32) for _ in range(3)]
    if invalid == "count":
        channels.pop()
    elif invalid == "shape":
        channels[1] = np.zeros((2, 3, 5), np.float32)
    elif invalid == "dimensions":
        channels = [np.zeros((2, 3), np.float32) for _ in range(3)]
    elif invalid == "empty":
        channels = [np.zeros((2, 3, 0), np.float32) for _ in range(3)]
    else:
        channels[1] = channels[1].astype(np.uint8)
    with pytest.raises(ValueError, match="Native argmax"):
        native_argmax(channels)
