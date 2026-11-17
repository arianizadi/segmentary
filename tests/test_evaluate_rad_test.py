"""CPU checks for the explicit test-evaluation boundary and audited pixel scoring."""

import hashlib
import json

import numpy as np
import pytest
from PIL import Image
from scripts import evaluate_rad_test as evaluate

from segmentary import gpu_policy


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_crop_excludes_added_padding_and_void_pixels():
    target = np.array([[0, 1, 255], [1, 0, 255]], dtype=np.uint8)
    padded = np.full((32, 32), 99, dtype=np.int64)
    padded[:2, :3] = [[0, 1, 0], [1, 0, 1]]
    pred = evaluate.cropped_prediction(padded, target.shape, 2)
    np.testing.assert_array_equal(evaluate.confusion(target, pred, 2), [[2, 0], [0, 2]])
    with pytest.raises(evaluate.TestEvaluationError, match="cropped"):
        evaluate.cropped_prediction(padded[:1], target.shape, 2)


def test_all_class_present_image_average_excludes_negative_image_false_positives():
    names = [f"class-{i}" for i in range(21)]
    samples, matrices = [], {}
    for c in range(21):
        key = str(c)
        matrix = np.zeros((21, 21), np.int64)
        matrix[c, 0 if c == 1 else c] = 1
        samples.append({"key": key, "class_pixels": {str(c): 1}})
        matrices[key] = matrix
    scored = evaluate.summarize(matrices, names, samples)
    assert scored["miou_present_images_classes"] == 21
    assert scored["miou_present_images"] == pytest.approx(20 / 21)
    # Class 0's false positive on class-1-only image is deliberately excluded.
    assert scored["per_class"]["class-0"]["iou"] == 1
    assert scored["per_class"]["class-1"]["iou"] == 0
    del matrices["20"]
    with pytest.raises(evaluate.TestEvaluationError, match="exactly the test"):
        evaluate.summarize(matrices, names, samples)


def test_confusion_must_match_audited_ground_truth_pixels():
    samples = [{"key": "a", "class_pixels": {"0": 2}}]
    with pytest.raises(evaluate.TestEvaluationError, match="audited"):
        evaluate.summarize({"a": np.eye(2, dtype=np.int64)}, ["a", "b"], samples)


def test_changed_test_mask_cannot_be_scored(tmp_path):
    rgb = tmp_path / "images/test/scene/a.png"
    mask = tmp_path / "masks/test/scene/a.png"
    rgb.parent.mkdir(parents=True)
    mask.parent.mkdir(parents=True)
    Image.fromarray(np.zeros((3, 5, 3), np.uint8)).save(rgb)
    target = np.zeros((3, 5), np.uint8)
    Image.fromarray(target).save(mask)
    sample = {
        "key": "scene/a",
        "image_extension": ".png",
        "image_sha256": sha(rgb),
        "mask_sha256": hashlib.sha256(target.tobytes()).hexdigest(),
        "width": 5,
        "height": 3,
        "class_pixels": {"0": 15},
    }
    evaluate.load_test_image(tmp_path, sample, 21)
    target[0, 0] = 1
    Image.fromarray(target).save(mask)
    with pytest.raises(evaluate.TestEvaluationError, match="Decoded test mask changed"):
        evaluate.load_test_image(tmp_path, sample, 21)


def test_request_requires_authorization_hash_and_frozen_gpu_identity(tmp_path, monkeypatch):
    config, checkpoint, state = [
        tmp_path / name for name in ["config.yaml", "final.ckpt", "state.json"]
    ]
    config.write_text("config")
    checkpoint.write_bytes(b"checkpoint")
    write(
        state,
        {
            "status": "completed",
            "checkpoints": {"final": {"path": str(checkpoint), "sha256": sha(checkpoint)}},
        },
    )
    campaign, request = tmp_path / "campaign.json", tmp_path / "request.json"
    job = {
        "name": "one",
        "config": str(config),
        "config_sha256": sha(config),
        "state_path": str(state),
        "final_checkpoint": str(checkpoint),
        "final_checkpoint_sha256": sha(checkpoint),
    }
    req = {
        "schema_version": 1,
        "test_evaluation_authorized": True,
        "campaign_json": str(campaign),
        "jobs": [job],
    }
    write(request, req)
    policy = gpu_policy.freeze(
        [0],
        [
            {"index": 0, "uuid": "GPU-aa", "pci_bus_id": "00:01"},
            {"index": 1, "uuid": "GPU-bb", "pci_bus_id": "00:02"},
        ],
        "unit-test",
    )
    write(
        campaign,
        {
            "request_sha256": sha(request),
            "gpu_policy": policy,
            "gpu_policy_sha256": gpu_policy.policy_sha256(policy),
        },
    )
    for k, v in gpu_policy.child_env({}, policy, 0, campaign).items():
        monkeypatch.setenv(k, v)
    evaluate.validate_request(request, "one", 0)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    with pytest.raises(gpu_policy.GpuPolicyError, match="exactly"):
        evaluate.validate_request(request, "one", 0)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    req["test_evaluation_authorized"] = False
    write(request, req)
    with pytest.raises(evaluate.TestEvaluationError, match="authorizing"):
        evaluate.validate_request(request, "one", 0)


def test_dataset_requires_every_class_before_model_inference(tmp_path):
    names = [f"c{i}" for i in range(21)]
    names[13] = "mud-pumping"
    splits = {"train": [], "val": [], "test": ["a"]}
    sample = {"key": "a", "split": "test", "image_sha256": "sha", "class_pixels": {"0": 1}}
    write(tmp_path / "splits.json", splits)
    write(tmp_path / "audit/samples.json", [sample])
    req = {
        "dataset_root": str(tmp_path),
        "split_sha256": sha(tmp_path / "splits.json"),
        "samples_sha256": sha(tmp_path / "audit/samples.json"),
        "class_names": names,
    }
    with pytest.raises(evaluate.TestEvaluationError, match="all 21 classes"):
        evaluate.validate_dataset(req, names)
