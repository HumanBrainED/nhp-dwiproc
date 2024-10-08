"""Helper functions for generating diffusion related files for workflow."""

import pathlib as pl
from typing import Any

import nibabel as nib
import numpy as np

from nhp_dwiproc.app import utils
from nhp_dwiproc.lib import metadata
from nhp_dwiproc.lib.utils import gen_hash


def get_phenc_info(
    idx: int,
    input_data: dict[str, Any],
    **kwargs,
) -> tuple[str, np.ndarray]:
    """Generate phase encode information file."""
    # Gather relevant metadata
    eff_echo = metadata.echo_spacing(dwi_json=input_data["dwi"]["json"], **kwargs)
    pe_dir = metadata.phase_encode_dir(
        idx=idx, dwi_json=input_data["dwi"]["json"], **kwargs
    )
    # Determine corresponding phase-encoding vector, set accordingly
    possible_vecs = {
        "i": np.array([1, 0, 0]),
        "j": np.array([0, 1, 0]),
        "k": np.array([0, 0, 1]),
    }
    pe_vec = possible_vecs[pe_dir[0]]
    if len(pe_dir) == 2 and pe_dir.endswith("-"):
        pe_vec[np.where(pe_vec > 0)] = -1

    # Generate phase encoding data for use
    img = nib.loadsave.load(input_data["dwi"]["nii"])
    img_size = np.array(img.header.get_data_shape())
    num_phase_encodes = img_size[np.where(np.abs(pe_vec) > 0)]
    pe_line = np.hstack([pe_vec, np.array(eff_echo * num_phase_encodes)])
    pe_data = np.array([pe_line])

    return pe_dir, pe_data


def concat_dir_phenc_data(
    pe_data: list[np.ndarray],
    input_group: dict[str, Any],
    cfg: dict[str, Any],
    **kwargs,
) -> pl.Path:
    """Concatenate opposite phase encoding directions."""
    phenc_fname = utils.bids_name(
        datatype="dwi", desc="concat", suffix="phenc", ext=".txt", **input_group
    )
    phenc_fpath = cfg["opt.working_dir"] / f"{gen_hash()}_concat-phenc" / phenc_fname
    phenc_fpath.parent.mkdir(parents=True, exist_ok=False)
    np.savetxt(phenc_fpath, np.vstack(pe_data), fmt="%.5f")

    return phenc_fpath


def normalize(
    img: str | pl.Path, input_group: dict[str, Any], cfg: dict[str, Any], **kwargs
) -> pl.Path:
    """Normalize 4D image."""
    nii = nib.loadsave.load(img)
    arr = np.array(nii.dataobj)

    ref_mean = np.mean(arr[..., 0])

    for idx in range(arr.shape[-1]):
        slice_mean = np.mean(arr[..., idx])
        if not np.isclose(slice_mean, 0.0):
            arr[..., idx] *= ref_mean / slice_mean

    norm_nii = nib.nifti1.Nifti1Image(dataobj=arr, affine=nii.affine, header=nii.header)

    nii_fname = utils.bids_name(
        datatype="dwi", desc="normalized", suffix="b0", ext=".nii.gz", **input_group
    )
    nii_fpath = cfg["opt.working_dir"] / f"{gen_hash()}_normalize" / nii_fname
    nii_fpath.parent.mkdir(parents=True, exist_ok=False)
    nib.loadsave.save(norm_nii, nii_fpath)

    return nii_fpath


def get_pe_indices(pe_dirs: list[str]) -> list[str]:
    """Get PE indices - LR/RL if available, AP otherwise."""
    indices: dict[str, list[Any]] = {"lr": [], "ap": []}
    pe: dict[str, list[Any]] = {
        "axe": [ax[0] for ax in pe_dirs],
        "dir": [ax[1:] for ax in pe_dirs],
    }

    # If multiple directions, use LR indices if possible, else use AP
    if len(set(pe_dirs)) > 1:
        for idx, ax in enumerate(pe["axe"]):
            idxes = idx + 1
            if ax == "i":
                indices["lr"].append(str(idxes))
            elif ax == "j":
                indices["ap"].append(str(idxes))
        return indices["lr"] if len(set(indices["lr"])) == 2 else indices["ap"]
    else:
        return ["1"] * len(pe["axe"])


def get_eddy_indices(
    niis: list[str | pl.Path],
    indices: list[str] | None,
    input_group: dict[str, Any],
    cfg: dict[str, Any],
) -> pl.Path:
    """Generate dwi index file for eddy."""
    imsizes = [nib.loadsave.load(nii).header.get_data_shape() for nii in niis]

    eddy_idxes = [
        idx if len(imsize) < 4 else [idx] * imsize[3]
        for idx, imsize in zip(indices or ["1"] * len(imsizes), imsizes)
    ]

    out_dir = cfg["opt.working_dir"] / f"{gen_hash()}_eddy-indices"
    out_fname = utils.bids_name(
        datatype="dwi", desc="eddy", suffix="indices", ext=".txt", **input_group
    )
    out_fpath = out_dir / out_fname
    out_fpath.parent.mkdir(parents=True, exist_ok=False)
    np.savetxt(out_fpath, np.array(eddy_idxes).flatten(), fmt="%s", newline=" ")

    return out_fpath


def rotate_bvec(
    bvec_file: pl.Path,
    transformation: pl.Path,
    cfg: dict[str, Any],
    input_group: dict[str, Any],
    **kwargs,
) -> pl.Path:
    """Rotate bvec file."""
    bvec = np.loadtxt(bvec_file)
    transformation_mat = np.loadtxt(transformation)
    rotated_bvec = np.dot(transformation_mat[:3, :3], bvec)

    out_dir = cfg["opt.working_dir"] / f"{gen_hash()}_rotate-bvec"
    out_fname = utils.bids_name(
        datatype="dwi",
        space="T1w",
        res="dwi",
        desc="preproc",
        suffix="dwi",
        ext=".bvec",
        **input_group,
    )
    out_fpath = out_dir / out_fname
    out_fpath.parent.mkdir(parents=True, exist_ok=False)
    np.savetxt(out_fpath, rotated_bvec, fmt="%.5f")

    return out_fpath
