"""A synthetic 3D CLI workflow spanning audit, split, prepare and evaluation."""

import json
import shutil

import nibabel as nib
import numpy as np

from segmentary.medical.cli import main


def test_native_volume_workflow_preserves_holdout_and_reports_per_case(tmp_path, capsys) -> None:
    source = tmp_path / "Task07_Pancreas"
    for folder in ("imagesTr", "labelsTr", "imagesTs"):
        (source / folder).mkdir(parents=True)
    affine = np.diag([1.25, 1.25, 2.5, 1.0])
    training = []
    for index in range(6):
        case_id = f"pancreas_{index:03}"
        image_path = source / "imagesTr" / f"{case_id}.nii.gz"
        label_path = source / "labelsTr" / f"{case_id}.nii.gz"
        image = np.random.default_rng(index).normal(30, 10, (16, 16, 16)).astype(np.float32)
        label = np.zeros(image.shape, dtype=np.uint8)
        label[3:12, 3:12, 3:12] = 1
        label[6:8, 7:9, 8:10] = 2
        for data, path in ((image, image_path), (label, label_path)):
            volume = nib.Nifti1Image(data, affine)
            volume.header.set_xyzt_units("mm")
            volume.set_qform(affine, code=1)
            volume.set_sform(affine, code=1)
            nib.save(volume, path)
        training.append(
            {"image": f"./imagesTr/{case_id}.nii.gz", "label": f"./labelsTr/{case_id}.nii.gz"}
        )
    (source / "dataset.json").write_text(
        json.dumps(
            {
                "numTraining": 6,
                "numTest": 0,
                "labels": {"0": "background", "1": "pancreas", "2": "cancer"},
                "training": training,
                "test": [],
            }
        )
    )
    manifest, splits = tmp_path / "manifest.json", tmp_path / "splits.json"
    assert main(["audit", "--dataset-root", str(source), "--output", str(manifest)]) == 0
    assert (
        main(
            [
                "split",
                "--manifest",
                str(manifest),
                "--output",
                str(splits),
                "--train-fraction",
                "0.5",
                "--val-fraction",
                "0.3333333333333333",
            ]
        )
        == 0
    )
    partitions = json.loads(splits.read_text())
    config, workspace = tmp_path / "config.yaml", tmp_path / "workspace"
    config.write_text(f"workspace: {workspace}\n")
    assert (
        main(
            [
                "prepare",
                "--config",
                str(config),
                "--manifest",
                str(manifest),
                "--splits",
                str(splits),
            ]
        )
        == 0
    )
    raw = workspace / "nnUNet_raw" / "Dataset707_Pancreas" / "imagesTr"
    assert len(list(raw.glob("*.nii.gz"))) == len(partitions["train"]) + len(partitions["val"])
    for case_id in partitions["test"]:
        assert not (raw / f"{case_id}_0000.nii.gz").exists()
    predictions, output = tmp_path / "predictions", tmp_path / "evaluation"
    predictions.mkdir()
    for case_id in partitions["val"]:
        shutil.copyfile(
            source / "labelsTr" / f"{case_id}.nii.gz", predictions / f"{case_id}.nii.gz"
        )
    assert (
        main(
            [
                "evaluate",
                "--manifest",
                str(manifest),
                "--splits",
                str(splits),
                "--predictions",
                str(predictions),
                "--output",
                str(output),
                "--surface-tolerance-mm",
                "1",
                "--bootstrap-samples",
                "20",
                "--review-overlays",
            ]
        )
        == 0
    )
    report = json.loads((output / "report.json").read_text())
    assert report["regions"]["mass"]["dice"]["mean"] == 1.0
    assert report["regions"]["mass"]["hd95_mm"]["mean"] == 0.0
    assert report["coverage"]["eligible_cases"] == len(partitions["val"])
    assert (
        main(
            [
                "report",
                "--input",
                str(output / "report.json"),
                "--output",
                str(output / "report.md"),
            ]
        )
        == 0
    )
    assert "| mass | 1.0000 |" in (output / "report.md").read_text()
    capsys.readouterr()
