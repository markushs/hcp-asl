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

from hcpasl.initial_bookkeeping import initial_processing
from hcpasl.m0_mt_correction import correct_M0
from hcpasl.asl_correction import hcp_asl_moco
from hcpasl.asl_differencing import tag_control_differencing
from hcpasl.asl_perfusion import run_fabber_asl, run_oxford_asl
from hcpasl.projection import project_to_surface
from pathlib import Path
import subprocess
import argparse
from multiprocessing import cpu_count

def process_subject(studydir, subid, mt_factors, mbpcasl, structural, surfaces, fmaps, 
                    gradients, use_t1=False, pvcorr=False, cores=cpu_count(), 
                    interpolation=3, use_sebased=False, wmparc=None, ribbon=None):
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
    use_t1 : bool, optional
        Whether or not to use the estimated T1 map in the 
        oxford_asl run in structural space.
    pvcorr : bool, optional
        Whether or not to run oxford_asl using pvcorr when 
        performing perfusion estimation in (ASL-gridded) T1 
        space.
    use_sebased : bool, optional
        Whether or not to use HCP's SE-based bias-correction 
        to refine the bias correction obtained using FAST at 
        the beginning of the pipeline. Default is False.
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
    """
    subject_dir = (studydir / subid).resolve(strict=True)
    initial_processing(subject_dir, mbpcasl=mbpcasl, structural=structural, surfaces=surfaces)
    correct_M0(subject_dir, mt_factors)
    hcp_asl_moco(subject_dir, mt_factors, cores=cores, interpolation=interpolation)
    for target in ('asl', 'structural'):
        dist_corr_call = [
            "hcp_asl_distcorr",
            "--study_dir", str(subject_dir.parent), 
            "--sub_id", subject_dir.stem,
            '--mtname', mt_factors,
            "--target", target, 
            "--grads", gradients,
            "--fmap_ap", fmaps['AP'], "--fmap_pa", fmaps['PA'],
            "--cores", str(cores), "--interpolation", str(interpolation)
        ]
        if use_t1 and (target=='structural'):
            dist_corr_call.append('--use_t1')
        if use_sebased and (target=='structural'):
            dist_corr_call.append('--sebased')
        subprocess.run(dist_corr_call, check=True)
        if target == 'structural':
            pv_est_call = [
                "pv_est",
                str(subject_dir.parent),
                subject_dir.stem,
                "--cores", str(cores)
            ]
            subprocess.run(pv_est_call, check=True)
        if use_sebased and (target=='structural'):
            calib_name = subject_dir/'T1w/ASL/Calib/Calib0/DistCorr/calib0_dcorr.nii.gz'
            asl_name = subject_dir/'T1w/ASL/TIs/DistCorr/tis_distcorr.nii.gz'
            mask_name = subject_dir/'T1w/ASL/reg/ASL_grid_T1w_acpc_dc_restore_brain_mask.nii.gz'
            fmapmag_name = subject_dir/'T1w/ASL/reg/fmap/fmapmag_aslstruct.nii.gz'
            out_dir = subject_dir/'T1w/ASL/TIs/BiasCorr'
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
        if use_sebased and (target=='structural'):
            series = subject_dir/'T1w/ASL/TIs/BiasCorr/tis_secorr.nii.gz'
        elif target=='structural':
            series = subject_dir/'T1w/ASL/TIs/DistCorr/tis_distcorr.nii.gz'
        else:
            series = subject_dir/'ASL/TIs/DistCorr/tis_distcorr.nii.gz'
        tag_control_differencing(series, subject_dir, target=target)
        run_oxford_asl(subject_dir, target=target, use_t1=use_t1, pvcorr=pvcorr)
        project_to_surface(subject_dir, target=target)

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
        required=True
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
        '--sebased',
        help="If this flag is provided, the distortion warps and motion "
            +"estimates will be applied to the MT-corrected but not bias-"
            +"corrected calibration and ASL images. The bias-field will "
            +"then be estimated from the calibration image using HCP's "
            +"SE-based algorithm and applied in subsequent steps.",
        action='store_true'
    )
    parser.add_argument(
        '--wmparc',
        help="wmparc.mgz from FreeSurfer for use in SE-based bias correction.",
        default=None,
        required="--sebased" in sys.argv
    )
    parser.add_argument(
        '--ribbon',
        help="ribbon.mgz from FreeSurfer for use in SE-based bias correction.",
        default=None,
        required="--sebased" in sys.argv
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
        "--fabberdir",
        help="User Fabber executable in <fabberdir>/bin/ for users"
            + "with FSL < 6.0.4"
    )
    # assign arguments to variables
    args = parser.parse_args()
    mtname = Path(args.mtname).resolve(strict=True)
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
                    use_sebased=args.sebased,
                    wmparc=args.wmparc,
                    ribbon=args.ribbon
                    )

if __name__ == '__main__':
    main()