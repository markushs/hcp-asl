import logging
import os
import os.path as op
import subprocess as sp
from pathlib import Path

import nibabel as nb
import numpy as np
import regtricks as rt
from fsl.wrappers import bet

from hcpasl.utils import sp_run


def generate_gdc_warp(vol, coeffs_path, distcorr_dir, interpolation=1):
    """
    Generate distortion correction warp via gradient_unwarp.

    Args:
        vol: path to first volume we wish to correct
        coeffs_path: path to coefficients file for the scanner (.grad)
        distcorr_dir: directory in which to put output
        interpolation: order of interpolation to be used, default is 1
                        (this is the gradient_unwarp.py default also)

    Returns:
        n/a, file 'fullWarp_abs.nii.gz' will be created in output dir
    """

    logging.info("Running generate_gdc_warp")
    logging.info(f"vol: {vol}")
    logging.info(f"coeffs_path: {coeffs_path}")
    logging.info(f"distcorr_dir: {distcorr_dir}")
    logging.info(f"interpolation: {interpolation}")

    cmd = "gradient_unwarp.py {} gdc_corr_vol1.nii.gz siemens -g {} --interp_order {}".format(
        vol, coeffs_path, interpolation
    )
    logging.info(f"Running gradient_unwarp.py in {distcorr_dir} with command {cmd}")
    sp_run(cmd, shell=True, cwd=distcorr_dir)
    logging.info("gradient_unwarp.py run is complete.")


def generate_topup_params(pars_filepath):
    """
    Generate a file containing the parameters used by topup
    """
    if os.path.isfile(pars_filepath):
        os.remove(pars_filepath)
    with open(pars_filepath, "a") as t_pars:
        t_pars.write("0 1 0 0.04845" + "\n")
        t_pars.write("0 -1 0 0.04845")


def stack_fmaps(pa_sefm, ap_sefm, savename):
    rt.ImageSpace.save_like(
        ref=pa_sefm,
        data=np.stack(
            (nb.load(pa_sefm).get_fdata(), nb.load(ap_sefm).get_fdata()), axis=-1
        ),
        path=savename,
    )


def apply_gdc_and_topup(
    pa_ap_sefms, topup_dir, gdc_warp, interpolation=3, gd_corr=True
):
    # load topup EPI distortion correction warps and motion correction
    topup_warps = [
        rt.NonLinearRegistration.from_fnirt(
            coefficients=warp_name,
            src=pa_ap_sefms,
            ref=pa_ap_sefms,
            intensity_correct=True,
        )
        for warp_name in [
            op.join(topup_dir, f"WarpField_{n}.nii.gz") for n in ("01", "02")
        ]
    ]
    topup_moco = rt.MotionCorrection.from_mcflirt(
        mats=[op.join(topup_dir, f"MotionMatrix_{n}.mat") for n in ("01", "02")],
        src=pa_ap_sefms,
        ref=pa_ap_sefms,
    )

    # load gradient_unwarp's gdc warp
    # use an affine identity registration if gd_corr==False
    if gd_corr:
        gdc_warp = rt.NonLinearRegistration.from_fnirt(
            coefficients=gdc_warp,
            src=pa_ap_sefms,
            ref=pa_ap_sefms,
            intensity_correct=True,
        )
    else:
        gdc_warp = rt.Registration.identity()

    # chain gdc, epidc and moco together to apply all together
    topup_gdc_dc_moco = [
        rt.chain(gdc_warp, topup_moco[n], topup_warps[n]) for n in range(0, 2)
    ]

    # load pa_ap_sefms
    pa_ap_sefms = nb.load(pa_ap_sefms)

    # apply corrections and save in stacked image
    pa_ap_sefms_gdc_dc = [
        topup_gdc_dc_moco[n].apply_to_array(
            data=pa_ap_sefms.get_fdata()[:, :, :, n],
            src=pa_ap_sefms,
            ref=pa_ap_sefms,
            order=interpolation,
        )
        for n in range(0, 2)
    ]
    pa_ap_sefms_gdc_dc = nb.nifti1.Nifti1Image(
        np.concatenate([arr[..., np.newaxis] for arr in pa_ap_sefms_gdc_dc], axis=-1),
        affine=pa_ap_sefms.affine,
    )
    return pa_ap_sefms_gdc_dc


def generate_fmaps(
    pa_ap_sefms, params, config, distcorr_dir, gdc_warp, interpolation=3, gd_corr=True
):
    """
    Generate fieldmaps via topup for use with asl_reg.

    Args:
        asl_vol0: path to image of stacked blipped images (ie, PEdir as vol0,
            (oPEdir as vol1), in this case stacked as pa then ap)
        params: path to text file for topup --datain, PE directions/times
        config: path to text file for topup --config, other args
        distcorr_dir: directory in which to put output
        gdc_warp: path to gradient_unwarp's gradient distortion correction warp
        interpolation: order of interpolation to be used when applying registrations,
            default=3
        gd_corr: Boolean whether to perform gradient distortion correction or not, default True

    Returns:
        n/a, files 'fmap, fmapmag, fmapmagbrain.nii.gz' will be created in output dir
    """
    logging.info("Running generate_fmaps()")
    logging.info(f"Spin Echo Field Maps: {pa_ap_sefms}")
    logging.info(f"Topup param file: {params}")
    logging.info(f"Topup config file: {config}")
    logging.info(f"Topup output directory: {distcorr_dir}")
    logging.info(f"Gradient distortion correction warp: {gdc_warp}")
    logging.info(f"Perform gradient distortion correction: {gd_corr}")
    logging.info(f"Interpolation order: {interpolation}")

    # apply gradient distortion correction to stacked SEFMs
    if gd_corr:
        gdc = rt.NonLinearRegistration.from_fnirt(
            coefficients=gdc_warp,
            src=pa_ap_sefms,
            ref=pa_ap_sefms,
            intensity_correct=True,
        )
        topup_input_pa_ap_sefms = gdc.apply_to_image(
            src=pa_ap_sefms, ref=pa_ap_sefms, order=interpolation, cores=1
        )
    else:
        topup_input_pa_ap_sefms = nb.load(pa_ap_sefms)
    topup_input_pa_ap_sefms_name = distcorr_dir / "merged_sefms_topup_input.nii.gz"
    nb.save(topup_input_pa_ap_sefms, topup_input_pa_ap_sefms_name)

    # Run topup to get fmap in Hz
    topup_fmap = op.join(distcorr_dir, "topup_fmap_hz.nii.gz")
    topup_cmd = [
        "topup",
        f"--imain={topup_input_pa_ap_sefms_name}",
        f"--datain={params}",
        f"--config={config}",
        f"--out={op.join(distcorr_dir, 'topup')}",
        f"--iout={op.join(distcorr_dir, 'corrected_sefms.nii.gz')}",
        f"--fout={topup_fmap}",
        f"--dfout={op.join(distcorr_dir, 'WarpField')}",
        f"--rbmout={op.join(distcorr_dir, 'MotionMatrix')}",
        f"--jacout={op.join(distcorr_dir, 'Jacobian')}",
        "--verbose",
    ]
    sp_run(topup_cmd)
    fmap, fmapmag, fmapmagbrain = [
        op.join(distcorr_dir, "{}.nii.gz".format(s))
        for s in ["fmap", "fmapmag", "fmapmagbrain"]
    ]

    # Convert fmap from Hz to rad/s
    logging.info("Converting fieldmap from Hz to rad/s.")
    fmap_spc = rt.ImageSpace(topup_fmap)
    fmap_arr_hz = nb.load(topup_fmap).get_fdata()
    fmap_arr = fmap_arr_hz * 2 * np.pi
    fmap_spc.save_image(fmap_arr, fmap)

    # Apply gdc warp from gradient_unwarp and topup's EPI-DC
    # warp (just generated) in one interpolation step
    logging.info(
        "Applying distortion correction to fieldmap images in one interpolation step."
    )
    pa_ap_sefms_gdc_dc = apply_gdc_and_topup(
        pa_ap_sefms,
        distcorr_dir,
        gdc_warp,
        interpolation=interpolation,
        gd_corr=gd_corr,
    )

    # Mean across volumes of corrected sefms to get fmapmag
    logging.info("Taking mean of corrected fieldmap images to get fmapmag.nii.gz")
    fmapmag_img = nb.nifti1.Nifti1Image(
        pa_ap_sefms_gdc_dc.get_fdata().mean(-1), affine=pa_ap_sefms_gdc_dc.affine
    )
    nb.save(fmapmag_img, fmapmag)

    # Run BET on fmapmag to get brain only version
    logging.info("Running BET on fmapmag for brain-extracted version.")
    bet(fmapmag, output=fmapmagbrain)


def register_fmap(fmapmag, fmapmagbrain, s, sbet, out_dir, wm_tissseg):
    # create output directory
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True, parents=True)

    # get schedule
    fsldir = os.environ.get("FSLDIR")
    schedule = Path(fsldir) / "etc/flirtsch/bbr.sch"

    # set up commands
    init_xform = out_dir / "fmapmag2struct_init.mat"
    sec_xform = out_dir / "fmapmag2struct_sec.mat"
    bbr_xform = out_dir / "fmapmag2struct_bbr.mat"
    init_cmd = [
        "flirt",
        "-in",
        fmapmagbrain,
        "-ref",
        sbet,
        "-dof",
        "6",
        "-omat",
        init_xform,
    ]
    sec_cmd = [
        "flirt",
        "-in",
        fmapmag,
        "-ref",
        s,
        "-dof",
        "6",
        "-init",
        init_xform,
        "-omat",
        sec_xform,
        "-nosearch",
    ]
    bbr_cmd = [
        "flirt",
        "-ref",
        s,
        "-in",
        fmapmag,
        "-dof",
        "6",
        "-cost",
        "bbr",
        "-wmseg",
        wm_tissseg,
        "-init",
        sec_xform,
        "-omat",
        bbr_xform,
        "-schedule",
        schedule,
    ]
    for cmd in (init_cmd, sec_cmd, bbr_cmd):
        sp.run(cmd)
    return str(bbr_xform)


def gradunwarp_and_topup(
    vol,
    coeffs_path,
    gradunwarp_dir,
    topup_dir,
    pa_sefm,
    ap_sefm,
    interpolation=1,
    force_refresh=True,
    gd_corr=True,
):
    """
    Run gradient_unwarp and topup.

    Parameters
    ----------
    vol: path to volume to correct
    coeffs_path: path to gradient coefficients
    gradunwarp_dir: Directory to save gradient_unwarp results
    topup_dir: Directory to save topup results
    pa_sefm: path to PA spin-echo fieldmap image
    ap_sefm: path to AP spin-echo fieldmap image
    interpolation: integer order for image interpolation, default 1
    force_refresh: Boolean whether to refresh already existing files, default True
    gd_corr: Boolean whether to perform gradient distortion correction or not, default True

    Returns
    -------
    n/a: Saves outputs to file in ${output_dir}/gradient_unwarp and
        ${output_dir}/topup.
    """

    # run gradient_unwarp
    if gd_corr:
        gradunwarp_dir.mkdir(exist_ok=True, parents=True)
        gdc_warp_name = gradunwarp_dir / "fullWarp_abs.nii.gz"
        logging.info("Running generate_gdc_warp().")
        if not gdc_warp_name.exists() or force_refresh:
            generate_gdc_warp(vol, coeffs_path, gradunwarp_dir, interpolation)
    else:
        gdc_warp_name = None

    # create topup results directory
    topup_dir.mkdir(exist_ok=True, parents=True)

    # stack raw fieldmap images for use in topup
    pa_ap_sefms = topup_dir / "merged_sefms.nii.gz"
    if not pa_ap_sefms.exists() or force_refresh:
        logging.info("Concatenating Spin Echo fieldmap images.")
        stack_fmaps(pa_sefm, ap_sefm, pa_ap_sefms)

    # generate topup params
    topup_params = topup_dir / "topup_params.txt"
    if not topup_params.exists() or force_refresh:
        logging.info(f"Generating topup parameter file: {topup_params}")
        generate_topup_params(topup_params)

    # run topup
    topup_config = "b02b0.cnf"
    fmap, fmapmag, fmapmagbrain = [
        topup_dir / f"fmap{ext}.nii.gz" for ext in ("", "mag", "magbrain")
    ]
    if not all([f.exists() for f in (fmap, fmapmag, fmapmagbrain)]) or force_refresh:
        generate_fmaps(
            pa_ap_sefms,
            topup_params,
            topup_config,
            topup_dir,
            gdc_warp_name,
            interpolation=interpolation,
            gd_corr=gd_corr,
        )


def generate_epidc_warp(
    asl_vol0_brain,
    struct,
    struct_brain,
    asl_mask,
    wmmask,
    asl2struct,
    fmap,
    fmapmag,
    fmapmagbrain,
    distcorr_dir,
    interpolation=3,
):
    """
    Generate EPI distortion correction warp via asl_reg.

    Args:
        asl_vol0_brain: path to first volume of ASL series, brain-extracted
        struct: path to T1 image, ac_dc_restore
        struct_brain: path to brain-extracted T1 image, ac_dc_restore_brain
        asl_mask: path to brain mask in ASL space
        wmmask: path to WM mask in T1 space
        asl2struct: regtricks.Registration for asl to structural
        fmap: path to topup's field map in rad/s
        fmapmag: path to topup's field map magnitude
        fmapmagbrain: path to topup's field map magnitude, brain only
        distcorr_dir: path to directory in which to place output

    Returns:
        n/a, file 'asl2struct_warp.nii.gz' is created in output directory
    """

    a2s_fsl = op.join(distcorr_dir, "asl2struct.mat")
    asl2struct.save_fsl(a2s_fsl, asl_vol0_brain, struct)

    # get linear registration from fieldmaps to structural
    fmap_struct_dir = op.join(distcorr_dir, "fmap_struct_reg")
    bbr_fmap2struct = register_fmap(
        fmapmag, fmapmagbrain, struct, struct_brain, fmap_struct_dir, wmmask
    )

    # apply linear registration to fmap, fmapmag and fmapmagbrain
    bbr_fmap2struct = rt.Registration.from_flirt(
        bbr_fmap2struct, src=fmapmag, ref=struct
    )
    fmap_struct, fmapmag_struct, fmapmagbrain_struct = [
        op.join(fmap_struct_dir, f"fmap{ext}_struct.nii.gz")
        for ext in ("", "mag", "magbrain")
    ]
    for fmap_name, fmapstruct_name in zip(
        (fmap, fmapmag, fmapmagbrain),
        (fmap_struct, fmapmag_struct, fmapmagbrain_struct),
    ):
        fmapstruct_img = bbr_fmap2struct.apply_to_image(
            fmap_name, struct, order=interpolation
        )
        nb.save(fmapstruct_img, fmapstruct_name)

    # run asl_reg using pre-registered fieldmap images
    cmd = (
        "asl_reg -i {} -o {} ".format(asl_vol0_brain, distcorr_dir)
        + "-s {} --sbet={} -m {} ".format(struct, struct_brain, asl_mask)
        + "--tissseg={} --imat={} --finalonly ".format(wmmask, a2s_fsl)
        + "--fmap={} --fmapmag={} ".format(fmap_struct, fmapmag_struct)
        + "--fmapmagbrain={} --nofmapreg ".format(fmapmagbrain_struct)
        + "--echospacing=0.00057 --pedir=y"
    )
    sp.run(cmd)
