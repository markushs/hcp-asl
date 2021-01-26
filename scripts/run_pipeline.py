"""
This script performs the full minimal pre-processing ASL pipeline 
for the Human Connectome Project (HCP) ASL data.

This currently requires that the script is called followed by 
the directories of the subjects of interest and finally the 
name of the MT correction scaling factors image.
"""

import sys
import os
from itertools import product

from hcpasl.initial_bookkeeping import initial_setup
from hcpasl.distortion_correction import gradunwarp_and_topup
from hcpasl.m0_mt_correction import correct_M0
from hcpasl.asl_correction import hcp_asl_moco
from hcpasl.asl_differencing import tag_control_differencing
from hcpasl.asl_perfusion import run_fabber_asl, run_oxford_asl
# from hcpasl.projection import project_to_surface
from pathlib import Path
import subprocess
import argparse
from multiprocessing import cpu_count
import nibabel as nb

def process_subject(studydir, subid, mt_factors, mbpcasl, structural, surfaces, 
                    fmaps, gradients, wmparc, ribbon, wbdevdir, use_t1=False, 
                    pvcorr=False, cores=cpu_count(), interpolation=3,
                    nobandingcorr=False, outdir="hcp_asl"):
    """
    Run the hcp-asl pipeline for a given subject.

    Parameters
    ----------
    studydir : pathlib.Path
        Path to the study's base directory.
    subid : str
        Subject id for the subject of interest.
    mt_factors : pathlib.Path
        Path to a .txt file of pre-calculated MT correction 
        factors.
    mbpcasl : pathlib.Path
        Path to the subject's mbPCASL sequence.
    structural : dict
        Contains pathlib.Path locations of important structural 
        files.
    surfaces : dict
        Contains pathlib.Path locations of the surfaces needed 
        for the pipeline.
    fmaps : dict
        Contains pathlib.Path locations of the fieldmaps needed 
        for distortion correction.
    gradients : str
        pathlib.Path to a gradient coefficients file for use in 
        gradient distortion correction.
    wmparc : str
        pathlib.Path to wmparc.nii.gz from FreeSurfer for use in 
        SE-based bias correction.
    ribbon : str
        pathlib.Path to ribbon.nii.gz from FreeSurfer for use in 
        SE-based bias correction.
    wbdevdir : str
        path to development version of wb_command's bin directory 
        e.g. workbench/bin_macosx64
    use_t1 : bool, optional
        Whether or not to use the estimated T1 map in the 
        oxford_asl run in structural space.
    pvcorr : bool, optional
        Whether or not to run oxford_asl using pvcorr when 
        performing perfusion estimation in (ASL-gridded) T1 
        space.
    cores : int, optional
        Number of cores to use.
        When applying motion correction, this is the number 
        of cores that will be used by regtricks. Default is 
        the number of cores on your machine.
    interpolation : int, optional
        The interpolation order to use for registrations.
        Regtricks passes this on to scipy's map_coordinates. 
        The meaning of the value can be found in the scipy 
        documentation. Default is 3.
    nobandingcorr : bool, optional
        If this is True, the banding correction options in the 
        pipeline will be switched off. Default is False (i.e. 
        banding corrections are applied by default).
    outdir : str, optional
        Name of the main results directory. Default is 'hcp_asl'.
    """

    subject_dir = (studydir / subid).resolve(strict=True)

    # initial set-up for the pipeline: create results directories; 
    # split mbPCASL sequence into TIs and calibration images; and 
    # return dictionary with locations of important files.
    names = initial_setup(subject_dir, 
                          mbpcasl=mbpcasl, 
                          structural=structural, 
                          surfaces=surfaces,
                          fmaps=fmaps,
                          outdir=outdir)

    # run gradient_unwarp and topup, storing results 
    # in gradunwarp_dir and topup_dir respectively
    print("Running gradient_unwarp and topup.")
    asl_dir = Path(names["ASL_dir"])
    gradunwarp_dir = asl_dir/"gradient_unwarp"
    topup_dir = asl_dir/"topup"
    gradunwarp_and_topup(vol=names["calib0_img"], 
                         coeffs_path=gradients, 
                         gradunwarp_dir=gradunwarp_dir, 
                         topup_dir=topup_dir, 
                         pa_sefm=names["pa_sefm"], 
                         ap_sefm=names["ap_sefm"], 
                         interpolation=interpolation)

    # apply corrections to the calibration images
    print("Running M0 corrections.")
    hcppipedir = Path(os.environ["HCPPIPEDIR"])
    corticallut = hcppipedir/'global/config/FreeSurferCorticalLabelTableLut.txt'
    subcorticallut = hcppipedir/'global/config/FreeSurferSubcorticalLabelTableLut.txt'
    correct_M0(subject_dir=subject_dir, 
               calib_dir=Path(names["calib_dir"]), 
               mt_factors=mt_factors, 
               t1w_dir=Path(names["T1w_dir"]), 
               aslt1w_dir=Path(names["structasl"]), 
               gradunwarp_dir=Path(gradunwarp_dir), 
               topup_dir=Path(topup_dir), 
               wmparc=wmparc, 
               ribbon=ribbon, 
               corticallut=corticallut, 
               subcorticallut=subcorticallut, 
               interpolation=interpolation, 
               nobandingcorr=nobandingcorr, 
               outdir=outdir)
    
    # correct ASL series for distortion, bias, motion and banding
    # giving an ASL series in ASL0 space
    print("Estimating ASL motion.")
    calib0_dir = Path(names["calib0_dir"])
    tis_dir = Path(names["TIs_dir"])
    bias_field = calib0_dir/"BiasCorr/calib0_bias.nii.gz"
    if not nobandingcorr:
        calib_corr = calib0_dir/"MTCorr/calib0_mtcorr.nii.gz"
    else:
        calib_corr = calib0_dir/"BiasCorr/calib0_restore.nii.gz"
    calib2struct = calib0_dir/"DistCorr/asl2struct.mat"
    hcp_asl_moco(subject_dir=subject_dir, 
                 tis_dir=tis_dir, 
                 mt_factors=mt_factors, 
                 bias_name=bias_field, 
                 calib_name=calib_corr, 
                 calib2struct=calib2struct, 
                 gradunwarp_dir=gradunwarp_dir, 
                 topup_dir=topup_dir, 
                 cores=cores, 
                 interpolation=interpolation, 
                 nobandingcorr=nobandingcorr, 
                 outdir=outdir)
    
    # perform tag-control subtraction in ASL0 space
    print("Performing tag-control subtraction of the corrected ASL series in ASL0 space.")
    if not nobandingcorr:
        series = tis_dir/"STCorr2/tis_stcorr.nii.gz"
        scaling_factors = tis_dir/"STCorr2/combined_scaling_factors.nii.gz"
    else:
        series = tis_dir/"MoCo/reg_gdc_dc_tis_biascorr.nii.gz"
        scaling_factors = tis_dir/"MoCo/combined_scaling_factors.nii.gz"
    betas_dir = tis_dir/"Betas"
    tag_control_differencing(series, scaling_factors, betas_dir, subject_dir, outdir)

    # estimate perfusion in ASL0 space using oxford_asl
    print("Running oxford_asl in ASL0 space.")
    beta_perf = betas_dir/"beta_perf.nii.gz"
    oxford_asl_dir = tis_dir/"OxfordASL"
    oxford_asl_call = [
        "oxford_asl",
        f"-i {str(betas_dir/'beta_perf.nii.gz')}", f"-o {str(oxford_asl_dir)}",
        f"-m {str(brain_mask)}", "--tis=1.7,2.2,2.7,3.2,3.7", 
        "--slicedt=0.059", "--sliceband=10", "--casl", 
        "--ibf=tis", "--iaf=diff", "--rpts=6,6,6,10,15",
        "--fixbolus", "--bolus=1.5", "--te=19",
        "--debug", "--spatial=off"
    ]
    if use_t1:
        est_t1 = tis_dir/"SatRecov2/spatial/mean_T1t_filt.nii.gz"
        oxford_asl_call = oxford_asl_call + f"--t1im {str(est_t1)}"
    oxford_asl_call = " ".join(oxford_asl_call)
    print(oxford_asl_call)
    subprocess.run(oxford_asl_call, shell=True)

    for target in ('asl', 'structural'):
        # apply distortion corrections and get into target space
        print("Running distcorr_warps")
        dist_corr_call = [
            "hcp_asl_distcorr",
            "--study_dir", str(subject_dir.parent), 
            "--sub_id", subject_dir.stem,
            "--target", target, 
            "--grads", gradients,
            "--fmap_ap", fmaps['AP'], "--fmap_pa", fmaps['PA'],
            "--cores", str(cores), "--interpolation", str(interpolation),
            "--outdir", outdir
        ]
        if use_t1 and (target=='structural'):
            dist_corr_call.append('--use_t1')
        if nobandingcorr:
            dist_corr_call.append('--nobandingcorr')
        else:
            dist_corr_call.append('--mtname')
            dist_corr_call.append(mt_factors)
        subprocess.run(dist_corr_call, check=True)
        if target == 'structural':
            # perform partial volume estimation
            pv_est_call = [
                "pv_est",
                str(subject_dir.parent),
                subject_dir.stem,
                "--cores", str(cores),
                "--outdir", outdir
            ]
            subprocess.run(pv_est_call, check=True)
            # estimate bias field using SE-based
            calib_name = subject_dir/outdir/'ASLT1w/Calib/Calib0/DistCorr/calib0_dcorr.nii.gz'
            asl_name = subject_dir/outdir/'ASLT1w/TIs/DistCorr/tis_distcorr.nii.gz'
            mask_name = subject_dir/outdir/'ASLT1w/reg/ASL_grid_T1w_acpc_dc_restore_brain_mask.nii.gz'
            fmapmag_name = subject_dir/outdir/'ASL/topup/fmap_struct_reg/fmapmag_aslstruct.nii.gz'
            out_dir = subject_dir/outdir/'ASLT1w/TIs/BiasCorr'
            hcppipedir = Path(os.environ["HCPPIPEDIR"])
            corticallut = hcppipedir/'global/config/FreeSurferCorticalLabelTableLut.txt'
            subcorticallut = hcppipedir/'global/config/FreeSurferSubcorticalLabelTableLut.txt'
            sebased_cmd = [
                'get_sebased_bias',
                '-i', calib_name,
                '--asl', asl_name,
                '-f', fmapmag_name,
                '-m', mask_name,
                '--wmparc', wmparc,
                '--ribbon', ribbon,
                '--corticallut', corticallut,
                '--subcorticallut', subcorticallut,
                '-o', out_dir,
                '--debug'
            ]
            subprocess.run(sebased_cmd, check=True)
            # reapply banding corrections now that the series has been bias corrected
            series = nb.load(subject_dir/outdir/'ASLT1w/TIs/BiasCorr/tis_secorr.nii.gz')
            scaling_factors = nb.load(subject_dir/outdir/'ASLT1w/TIs/DistCorr/combined_scaling_factors.nii.gz')
            series_corr = nb.nifti1.Nifti1Image(series.get_fdata()*scaling_factors.get_fdata(),
                                                affine=series.affine)
            series = subject_dir/outdir/'ASLT1w/TIs/BiasCorr/tis_secorr_corr.nii.gz'
            nb.save(series_corr, series)
            if not nobandingcorr:
                calib = nb.load(subject_dir/outdir/'ASLT1w/TIs/BiasCorr/calib0_secorr.nii.gz')
                mt_sfs = nb.load(subject_dir/outdir/'ASLT1w/Calib/Calib0/DistCorr/mt_scaling_factors_calibstruct.nii.gz')
                calib_corr = nb.Nifti1Image(calib.get_fdata()*mt_sfs.get_fdata(), affine=calib.affine)
                calib_corr_name = subject_dir/outdir/'ASLT1w/TIs/BiasCorr/calib0_corr.nii.gz'
                nb.save(calib_corr, calib_corr_name)
        elif not nobandingcorr:
            # get name of series if target space is ASL
            series = subject_dir/outdir/'ASL/TIs/STCorr2/tis_stcorr.nii.gz'
        else:
            series = subject_dir/outdir/'ASL/TIs/MoCo/reg_gdc_dc_tis_biascorr.nii.gz'
        
        # perform differencing accounting for scaling
        tag_control_differencing(series, subject_dir, target=target, nobandingcorr=nobandingcorr, outdir=outdir)
        
        # estimate perfusion
        run_oxford_asl(subject_dir, target=target, use_t1=use_t1, pvcorr=pvcorr, outdir=outdir)

        # project perfusion results
        if target == 'structural':
            project_to_surface(studydir, subid, outdir=outdir, wbdevdir=wbdevdir)

def project_to_surface(studydir, subid, outdir, wbdevdir, lowresmesh="32", FinalASLRes="2.5", 
                       SmoothingFWHM="2", GreyOrdsRes="2", RegName="MSMSulc"):
    """
    Project perfusion results to the cortical surface and generate
    CIFTI representation which includes both low res mesh surfaces
    in MSMSulc Atlas space, and subcortical structures in MNI 
    voxel space

    Parameters
    ----------
    studydir : pathlib.Path
        Path to the study's base directory.
    subid : str
        Subject id for the subject of interest.
    """
    # Projection scripts path:
    script         = "PerfusionCIFTIProcessingPipeline.sh"
    wb_path        = str(Path(wbdevdir).resolve(strict=True))

    ASLVariable    = ["perfusion_calib", "arrival"]
    ASLVariableVar = ["perfusion_var_calib", "arrival_var"]

    for idx in range(2):
        non_pvcorr_cmd = [script, studydir, subid, ASLVariable[idx], ASLVariableVar[idx], lowresmesh,
                FinalASLRes, SmoothingFWHM, GreyOrdsRes, RegName, wb_path, "false", outdir]

        pvcorr_cmd = [script, studydir, subid, ASLVariable[idx], ASLVariableVar[idx], lowresmesh,
                FinalASLRes, SmoothingFWHM, GreyOrdsRes, RegName, wb_path, "true", outdir]
        
        subprocess.run(non_pvcorr_cmd)
        subprocess.run(pvcorr_cmd)

def main():
    """
    Main entry point for the hcp-asl pipeline.
    """
    # argument handling
    parser = argparse.ArgumentParser(
        description="This script performs the minimal processing for the "
                    + "HCP-Aging ASL data.")
    parser.add_argument(
        "--studydir",
        help="Path to the study's base directory.",
        required=True
    )
    parser.add_argument(
        "--subid",
        help="Subject id for the subject of interest.",
        required=True
    )
    parser.add_argument(
        "--mtname",
        help="Filename of the empirically estimated MT-correction"
            + "scaling factors.",
        required=not "--nobandingcorr" in sys.argv
    )
    parser.add_argument(
        "-g",
        "--grads",
        help="Filename of the gradient coefficients for gradient"
            + "distortion correction.",
        required=True
    )
    parser.add_argument(
        "-s",
        "--struct",
        help="Filename for the acpc-aligned, dc-restored structural image.",
        required=True
    )
    parser.add_argument(
        "--sbrain",
        help="Filename for the brain-extracted acpc-aligned, "
            + "dc-restored structural image.",
        required=True
    )
    parser.add_argument(
        "--surfacedir",
        help="Directory containing the 32k surfaces. These will be used for "
            +"the ribbon-constrained projection. If this argument is "
            +"provided, it is assumed that the surface names follow the "
            +"convention ${surfacedir}/{subjectid}_V1_MR.{side}.{surface}."
            +"32k_fs_LR.surf.gii.",
        required=False
    )
    parser.add_argument(
        "--lmid",
        help="Filename for the 32k left mid surface. This argument is "
            +"required if the '--surfacedir' argument is not provided.",
        required="--surfacedir" not in sys.argv
    )
    parser.add_argument(
        "--rmid",
        help="Filename for the 32k right mid surface. This argument is "
            +"required if the '--surfacedir' argument is not provided.",
        required="--surfacedir" not in sys.argv
    )
    parser.add_argument(
        "--lwhite",
        help="Filename for the 32k left white surface. This argument is "
            +"required if the '--surfacedir' argument is not provided.",
        required="--surfacedir" not in sys.argv
    )
    parser.add_argument(
        "--rwhite",
        help="Filename for the 32k right white surface. This argument is "
            +"required if the '--surfacedir' argument is not provided.",
        required="--surfacedir" not in sys.argv
    )
    parser.add_argument(
        "--lpial",
        help="Filename for the 32k left pial surface. This argument is "
            +"required if the '--surfacedir' argument is not provided.",
        required="--surfacedir" not in sys.argv
    )
    parser.add_argument(
        "--rpial",
        help="Filename for the 32k right pial surface. This argument is "
            +"required if the '--surfacedir' argument is not provided.",
        required="--surfacedir" not in sys.argv
    )
    parser.add_argument(
        "--mbpcasl",
        help="Filename for the mbPCASLhr acquisition.",
        required=True
    )
    parser.add_argument(
        "--fmap_ap",
        help="Filename for the AP fieldmap for use in distortion correction",
        required=True
    )
    parser.add_argument(
        "--fmap_pa",
        help="Filename for the PA fieldmap for use in distortion correction",
        required=True
    )
    parser.add_argument(
        '--use_t1',
        help="If this flag is provided, the T1 estimates from the satrecov "
            + "will also be registered to ASL-gridded T1 space for use in "
            + "perfusion estimation via oxford_asl.",
        action='store_true'
    )
    parser.add_argument(
        '--pvcorr',
        help="If this flag is provided, oxford_asl will be run using the "
            + "--pvcorr flag.",
        action='store_true'
    )
    parser.add_argument(
        '--wmparc',
        help="wmparc.mgz from FreeSurfer for use in SE-based bias correction.",
        default=None,
        required=True
    )
    parser.add_argument(
        '--ribbon',
        help="ribbon.mgz from FreeSurfer for use in SE-based bias correction.",
        default=None,
        required=True
    )
    parser.add_argument(
        "-c",
        "--cores",
        help="Number of cores to use when applying motion correction and "
            +"other potentially multi-core operations. Default is the "
            +f"number of cores your machine has ({cpu_count()}).",
        default=cpu_count(),
        type=int,
        choices=range(1, cpu_count()+1)
    )
    parser.add_argument(
        "--interpolation",
        help="Interpolation order for registrations. This can be any "
            +"integer from 0-5 inclusive. Default is 3. See scipy's "
            +"map_coordinates for more details.",
        default=3,
        type=int,
        choices=range(0, 5+1)
    )
    parser.add_argument(
        "--nobandingcorr",
        help="If this option is provided, the MT and ST banding corrections "
            +"won't be applied. This is to be used to compare the difference "
            +"our banding corrections make.",
        action="store_true"
    )
    parser.add_argument(
        "--fabberdir",
        help="User Fabber executable in <fabberdir>/bin/ for users"
            + "with FSL < 6.0.4"
    )
    parser.add_argument(
        "--wbdevdir",
        help="Location of development version of wb_command/bin_macosx64 "
            +"(dev_latest from 8th Dec 2020).",
        required=True
    )
    parser.add_argument(
        "--outdir",
        help="Name of the directory within which we will store all of the "
            +"pipeline's outputs in sub-directories. Default is 'hcp_asl'",
        default="hcp_asl"
    )
    # assign arguments to variables
    args = parser.parse_args()
    if args.mtname:
        mtname = Path(args.mtname).resolve(strict=True)
    else:
        mtname = None
    studydir = Path(args.studydir).resolve(strict=True)
    subid = args.subid
    structural = {'struct': args.struct, 'sbrain': args.sbrain}
    mbpcasl = Path(args.mbpcasl).resolve(strict=True)
    fmaps = {
        'AP': Path(args.fmap_ap).resolve(strict=True), 
        'PA': Path(args.fmap_pa).resolve(strict=True)
    }
    grads = Path(args.grads).resolve(strict=True)
    # surfaces
    if args.surfacedir:
        surfacedir = Path(args.surfacedir).resolve(strict=True)
        sides = ("L", "R")
        surfaces = ("midthickness", "pial", "white")
        lmid, lpial, lwhite, rmid, rpial, rwhite = [
            surfacedir / f"{subid}_V1_MR.{side}.{surf}.32k_fs_LR.surf.gii"
            for side, surf in product(sides, surfaces)
        ]
    else:
        lmid, lpial, lwhite, rmid, rpial, rwhite = [
            Path(arg).resolve(strict=True) for arg in (args.lmid, args.lpial, args.lwhite, 
                                                       args.rmid, args.rpial, args.rwhite)
        ]
    surfaces = {
        'L_mid': lmid, 'R_mid': rmid,
        'L_white': lwhite, 'R_white':rwhite,
        'L_pial': lpial, 'R_pial': rpial
    }
    if args.fabberdir:
        if not os.path.isfile(os.path.join(args.fabberdir, "bin", "fabber_asl")):
            print("ERROR: specified Fabber in %s, but no fabber_asl executable found in %s/bin" % (args.fabberdir, args.fabberdir))
            sys.exit(1)

        # To use a custom Fabber executable we set the FSLDEVDIR environment variable
        # which prioritises executables in $FSLDEVDIR/bin over those in $FSLDIR/bin.
        # Note that this could cause problems in the unlikely event that the user
        # already has a $FSLDEVDIR set up with custom copies of other things that
        # oxford_asl uses...
        print("Using Fabber-ASL executable %s/bin/fabber_asl" % args.fabberdir)
        os.environ["FSLDEVDIR"] = os.path.abspath(args.fabberdir)

    # create main results directory
    Path(args.outdir).mkdir(exist_ok=True)

    # process subject
    print(f"Processing subject {studydir/subid}.")
    process_subject(studydir=studydir,
                    subid=subid,
                    mt_factors=mtname,
                    cores=args.cores,
                    interpolation=args.interpolation,
                    gradients=grads,
                    mbpcasl=mbpcasl,
                    structural=structural,
                    surfaces=surfaces,
                    fmaps=fmaps,
                    use_t1=args.use_t1,
                    pvcorr=args.pvcorr,
                    wmparc=args.wmparc,
                    ribbon=args.ribbon,
                    nobandingcorr=args.nobandingcorr,
                    outdir=args.outdir,
                    wbdevdir=args.wbdevdir
                    )

if __name__ == '__main__':
    main()