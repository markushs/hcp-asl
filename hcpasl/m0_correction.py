"""
This contains a range of functions required to correct for the 
Magnetisation Transfer effect visible in the HCP data.
"""
import logging
import os.path as op
from pathlib import Path

import nibabel as nb
import numpy as np
import regtricks as rt

from .tissue_masks import generate_tissue_mask
from .utils import sp_run


def generate_asl2struct(asl_vol0, struct, fsdir, reg_dir):
    """
    Generate the linear transformation between ASL-space and T1w-space
    using FS bbregister. Note that struct is required only for saving
    the output in the right convention, it is not actually used by
    bbregister.

    Args:
        asl_vol0: path to first volume of ASL
        struct: path to T1w image (eg T1w_acdc_restore.nii.gz)
        fsdir: path to subject's FreeSurfer output directory
        reg_dir: path to registration directory, for output

    Returns:
        n/a, file 'asl2struct.mat' will be saved in reg_dir
    """

    logging.info("Running generate_asl2struct()")
    logging.info(f"Movable volume: {asl_vol0}")
    logging.info(f"T1w structural image: {struct}")
    logging.info(f"FreeSurfer output directory: {fsdir}")
    logging.info(f"Output directory: {reg_dir}")

    # We need to do some hacky stuff to get bbregister to work...
    # Split the path to the FS directory into a fake $SUBJECTS_DIR
    # and subject_id. We temporarily set the environment variable
    # before making the call, and then revert back afterwards
    new_sd, sid = op.split(fsdir)
    orig_mgz = op.join(fsdir, "mri", "orig.mgz")

    # Save the output in fsl format, by default
    # this targets the orig.mgz, NOT THE T1 IMAGE ITSELF!
    logging.info(f"Running bbregister in {reg_dir}; setting $SUBJECTS_DIR to {new_sd}")
    omat_path = op.join(reg_dir, "asl2struct.mat")
    cmd = f"$FREESURFER_HOME/bin/bbregister --s {sid} --mov {asl_vol0} --t2 "
    cmd += f"--reg asl2orig_mgz_initial_bbr.dat --fslmat {omat_path} --init-fsl"
    fslog_name = op.join(reg_dir, "asl2orig_mgz_initial_bbr.dat.log")
    logging.info(f"FreeSurfer's bbregister log: {fslog_name}")
    sp_run(cmd, shell=True, env={"SUBJECTS_DIR": new_sd}, cwd=reg_dir)

    # log final .dat transform
    with open(omat_path, "r") as f:
        lines = f.readlines()
        for line in lines:
            logging.info(line)

    # log minimum registration cost
    mincost = np.loadtxt(op.join(reg_dir, "asl2orig_mgz_initial_bbr.dat.mincost"))
    logging.info(f"bbregister's mincost: {mincost[0]:4f}")

    # convert .dat to .mat
    try:
        asl2orig_fsl = rt.Registration.from_flirt(omat_path, asl_vol0, orig_mgz)
    except RuntimeError as e:
        # final row != [0 0 0 1], round to 5 d.p. and try again
        logging.warning("FSL .mat file has an invalid format. Rounding to 5 d.p.")
        arr = np.loadtxt(omat_path)
        np.savetxt(omat_path, arr, fmt="%.5f")
        asl2orig_fsl = rt.Registration.from_flirt(omat_path, asl_vol0, orig_mgz)

    # Return to original working directory, and flip the FSL matrix to target
    # asl -> T1, not orig.mgz. Save output.
    logging.info("Converting .mat to target T1w.nii.gz rather than orig.mgz.")
    asl2struct_fsl = asl2orig_fsl.to_flirt(asl_vol0, struct)
    np.savetxt(op.join(reg_dir, "asl2struct.mat"), asl2struct_fsl)


def correct_M0(
    subject_dir,
    calib_dir,
    mt_factors,
    t1w_dir,
    aslt1w_dir,
    gradunwarp_dir,
    topup_dir,
    wmparc,
    ribbon,
    corticallut,
    subcorticallut,
    interpolation=3,
    nobandingcorr=False,
    outdir="hcp_asl",
    gd_corr=True,
):
    """
    Correct the M0 images.

    For each of the subject's two calibration images:
    #. Apply gradient and epi distortion corrections;
    #. Apply MT banding correction;
    #. Estimate registration to structural using FreeSurfer's bbregister;
    #. Use SE-based on the gdc_dc calibration image to obtain the bias-field;
    #. Apply bias correction and MT banding correction to gdc_dc calibration image.

    Parameters
    ----------
    subject_dir : pathlib.Path
        Path to the subject's base directory.
    calib_dir : pathlib.Path
        Path to the subject's ASL/Calib directory.
    mt_factors : pathlib.Path
        Path to the empirically estimated MT correction
        scaling factors.
    t1w_dir : pathlib.Path
        Path to the subject's T1w directory (within the
        Structural_preproc directory).
    aslt1w_dir : pathlib.Path
        Path to the subject's structural output directory, for
        example ${SubjectDir}/${OutDir}/T1w/ASL.
    gradunwarp_dir : pathlib.Path
        Path to the subject's gradient_unwarp run, for example
        ${SubjectDir}/${OutDir}/ASL/gradient_unwarp.
    topup_dir : pathlib.Path
        Path to the subject's topup run, for example
        ${SubjectDir}/${OutDir}/ASL/topup.
    wmparc : pathlib.Path
        Path to the subject's wmparc.nii.gz FreeSurfer output for
        use in SE-based bias correction.
    ribbon : pathlib.Path
        Path to the subject's ribbon.nii.gz FreeSurfer output for
        use in SE-based bias correction.
    corticallut : pathlib.Path
        FreeSurferCorticalLabelTableLut.txt for use in SE-based
        bias correction.
    subcorticallut : pathlib.Path
        FreeSurferSubcorticalLabelTableLut.txt for use in SE-based
        bias correction.
    interpolation : int, {0, 5}
        Order of interpolation to use when applying transformations.
        Default is 3.
    nobandingcorr : bool, optional
        If this is True, the banding correction options in the
        pipeline will be switched off. Default is False (i.e.
        banding corrections are applied by default).
    outdir : str
        Name of the main results directory. Default is 'hcp_asl'.
    gd_corr: bool
        Whether to perform gradient distortion correction or not.
        Default is True
    """

    # get calibration image names
    calib0, calib1 = [
        (calib_dir / f"Calib{n}/calib{n}.nii.gz").resolve(strict=True)
        for n in ("0", "1")
    ]

    # get structural image names
    struct_name, struct_brain_name = [
        (t1w_dir / f"T1w_acpc_dc_restore{suf}.nii.gz").resolve(strict=True)
        for suf in ("", "_brain")
    ]

    # generate white matter mask in T1w space for use in registration
    logging.info("Generating white matter mask in T1w space.")
    t1reg_dir = aslt1w_dir / "reg"
    t1reg_dir.mkdir(exist_ok=True, parents=True)
    aparc_aseg = (t1w_dir / "aparc+aseg.nii.gz").resolve(strict=True)
    wmmask_img = generate_tissue_mask(aparc_aseg, "wm")
    wmmask_name = t1reg_dir / "wmmask.nii.gz"
    nb.save(wmmask_img, wmmask_name)

    # load gradient distortion correction warp, fieldmaps and PA epidc warp
    logging.info("Loading gradient and EPI distortion correction warps.")
    gdc_name = (gradunwarp_dir / "fullWarp_abs.nii.gz").resolve()
    if gd_corr:
        logging.info(f"gradient_unwarp.py was run, loading {gdc_name}")
        gdc_warp = rt.NonLinearRegistration.from_fnirt(
            coefficients=gdc_name,
            src=calib0,
            ref=calib0,
            intensity_correct=True,
        )
    else:
        logging.info(
            f"gradient_unwarp.py was not run, not applying gradient distortion correction."
        )
    fmap, fmapmag, fmapmagbrain = [
        topup_dir / f"fmap{ext}.nii.gz" for ext in ("", "mag", "magbrain")
    ]
    epi_dc_warp = rt.NonLinearRegistration.from_fnirt(
        coefficients=topup_dir / "WarpField_01.nii.gz",
        src=fmap,
        ref=fmap,
        intensity_correct=True,
    )

    # register fieldmapmag to structural image for use in SE-based later
    logging.info("Getting registration from fmapmag image to structural image.")
    fmap_struct_dir = topup_dir / "fmap_struct_reg"
    Path(fmap_struct_dir).mkdir(exist_ok=True, parents=True)
    fsdir = (t1w_dir / subject_dir.stem).resolve(strict=True)
    generate_asl2struct(fmapmag, struct_name, fsdir, fmap_struct_dir)
    logging.info("Loading registration from fieldmap to struct.")
    bbr_fmap2struct = rt.Registration.from_flirt(
        fmap_struct_dir / "asl2struct.mat", src=fmapmag, ref=struct_name
    )

    # iterate over the two calibration images, applying the corrections to both
    logging.info("Iterating over subject's calibration images.")
    for calib_name in (calib0, calib1):
        # get calib_dir and other info
        calib_dir = calib_name.parent
        calib_name_stem = calib_name.stem.split(".")[0]
        logging.info(f"Processing {calib_name_stem}.")
        distcorr_dir = calib_dir / "DistCorr"
        distcorr_dir.mkdir(exist_ok=True, parents=True)

        # apply gdc to the calibration image
        if gd_corr:
            logging.info(
                f"Applying gradient distortion correction to {calib_name_stem}."
            )
            calib_img = gdc_warp.apply_to_image(
                calib_name, calib_name, order=interpolation
            )
            calib_name_stem = "gdc_" + calib_name_stem
            calib_corr_name = distcorr_dir / f"{calib_name_stem}.nii.gz"
            nb.save(calib_img, calib_corr_name)
        else:
            calib_corr_name = calib_name
            calib_img = nb.load(calib_corr_name)

        # apply mt scaling factors to the (potentially) gradient distortion-corrected calibration image
        if not nobandingcorr:
            logging.info(f"Applying MT scaling factors to {calib_name_stem}.")
            mt_sfs = np.loadtxt(mt_factors)
            assert len(mt_sfs) == calib_img.shape[2]
            mt_gdc_calib_img = nb.nifti1.Nifti1Image(
                calib_img.get_fdata() * mt_sfs, calib_img.affine
            )
            mtcorr_dir = calib_dir / "MTCorr"
            mtcorr_dir.mkdir(exist_ok=True, parents=True)
            calib_name_stem = "mtcorr_" + calib_name_stem
            calib_corr_name = mtcorr_dir / f"{calib_name_stem}.nii.gz"
            nb.save(mt_gdc_calib_img, calib_corr_name)

        # get registration to structural
        logging.info("Generate registration to structural.")
        generate_asl2struct(calib_corr_name, struct_name, fsdir, distcorr_dir)
        asl2struct_reg = rt.Registration.from_flirt(
            src2ref=distcorr_dir / "asl2struct.mat",
            src=calib_corr_name,
            ref=struct_name,
        )
        # invert for struct2calib registration
        struct2calib_reg = asl2struct_reg.inverse()
        struct2calib_name = distcorr_dir / "struct2asl.mat"
        np.savetxt(
            struct2calib_name,
            struct2calib_reg.to_flirt(struct_name, calib_corr_name),
        )

        # now that we have registrations from calib2str and fmap2str, use
        # this to apply gdc, epidc and MT correction to the calibration image
        # apply distortion corrections
        calib_name_stem = calib_name_stem.split("_")[-1]
        logging.info(f"Applying distortion corrections to {calib_name_stem}.")
        fmap2calib_reg = rt.chain(bbr_fmap2struct, struct2calib_reg)
        dc_calibspc_warp = rt.chain(
            fmap2calib_reg.inverse(), epi_dc_warp, fmap2calib_reg
        )
        if gd_corr:
            dc_calibspc_warp = rt.chain(gdc_warp, dc_calibspc_warp)
            calib_name_stem = "gdc_dc_" + calib_name_stem
        else:
            calib_name_stem = "dc_" + calib_name_stem
        dc_calib_name = distcorr_dir / f"{calib_name_stem}.nii.gz"
        dc_calib = dc_calibspc_warp.apply_to_image(
            src=calib_name, ref=calib_name, order=interpolation
        )
        nb.save(dc_calib, dc_calib_name)

        # register fmapmag to calibration image space to perform SE-based bias estimation
        logging.info(f"Registering {fmapmag.stem} to {calib_name_stem}")
        fmapmag_calibspc = fmap2calib_reg.apply_to_image(
            fmapmag, calib_name, order=interpolation
        )
        biascorr_dir = calib_dir / "BiasCorr"
        sebased_dir = biascorr_dir / "SEbased"
        sebased_dir.mkdir(parents=True, exist_ok=True)
        fmapmag_cspc_name = sebased_dir / f"fmapmag_{calib_name_stem}spc.nii.gz"
        nb.save(fmapmag_calibspc, fmapmag_cspc_name)

        # get brain mask in calibration image space
        logging.info("Getting brain mask in calibration image space.")
        fs_brainmask = (t1w_dir / "brainmask_fs.nii.gz").resolve(strict=True)
        aslfs_mask_name = calib_dir / "aslfs_mask.nii.gz"
        aslfs_mask = struct2calib_reg.apply_to_image(
            src=fs_brainmask, ref=calib_name, order=1
        )
        aslfs_mask = nb.nifti1.Nifti1Image(
            (aslfs_mask.get_fdata() > 0.5).astype(np.float32), affine=dc_calib.affine
        )
        nb.save(aslfs_mask, aslfs_mask_name)

        # get sebased bias estimate
        sebased_cmd = [
            "get_sebased_bias_asl",
            "-i",
            dc_calib_name,
            "-f",
            fmapmag_cspc_name,
            "-m",
            aslfs_mask_name,
            "-o",
            sebased_dir,
            "--ribbon",
            ribbon,
            "--wmparc",
            wmparc,
            "--corticallut",
            corticallut,
            "--subcorticallut",
            subcorticallut,
            "--struct2calib",
            struct2calib_name,
            "--structural",
            struct_name,
            "--debug",
        ]
        logging.info(f"Running SE-based bias estimation on {calib_name_stem}.")
        sp_run(sebased_cmd)

        # apply dilall to bias estimate
        bias_name = sebased_dir / "sebased_bias_dil.nii.gz"
        dilall_name = biascorr_dir / f"{calib_name_stem}_bias.nii.gz"
        dilall_cmd = ["fslmaths", bias_name, "-dilall", dilall_name]
        sp_run(dilall_cmd)

        # bias correct and mt correct the distortion corrected calib image
        logging.info(f"Performing bias correction.")
        bias_img = nb.load(dilall_name)
        bc_calib = nb.nifti1.Nifti1Image(
            dc_calib.get_fdata() / bias_img.get_fdata(), dc_calib.affine
        )
        biascorr_name = biascorr_dir / f"{calib_name_stem}_restore.nii.gz"
        nb.save(bc_calib, biascorr_name)

        if not nobandingcorr:
            logging.info(f"Performing MT correction.")
            mt_bc_calib = nb.nifti1.Nifti1Image(
                bc_calib.get_fdata() * mt_sfs, bc_calib.affine
            )
            mtcorr_name = mtcorr_dir / f"mtcorr_{calib_name_stem}_restore.nii.gz"
            nb.save(mt_bc_calib, mtcorr_name)
