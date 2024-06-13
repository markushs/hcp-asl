import os
import subprocess

from setuptools import find_packages, setup

PACKAGE_NAME = "hcpasl"
ROOTDIR = os.path.abspath(os.path.dirname(__file__))

def get_requirements():
    """Get a list of all entries in the requirements file"""
    with open(os.path.join(ROOTDIR, "requirements.txt"), encoding="utf-8") as f:
        return [l.strip() for l in f.readlines()]

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name=PACKAGE_NAME,
    version="1.0.0",
    author="Flora Kennedy McConnell, Jack Toner, Thomas Kirk",
    author_email="thomas.kirk1@nottingham.ac.uk",
    description="Minimal ASL processing pipeline for the HCP Lifespan datasets",
    long_description=long_description,
    url="https://github.com/physimals/hcp-asl",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=get_requirements(),
    entry_points={
        "console_scripts": [
            "process_hcp_asl = scripts.run_pipeline:main",
            "get_sebased_bias_asl = scripts.se_based:se_based_bias_estimation",
            "mt_estimation_asl = scripts.mt_estimation_pipeline:main",
            "results_to_mni_asl = scripts.results_to_mni:main",
        ]
    },
    scripts=[
        "scripts/VolumetoSurfaceASL.sh",
        "scripts/SurfaceSmoothASL.sh",
        "scripts/SubcorticalProcessingASL.sh",
        "scripts/PerfusionCIFTIProcessingPipelineASL.sh",
        "scripts/CreateDenseScalarASL.sh",
    ],
    package_data={
        "hcpasl": [
            "resources/scaling_factors.txt",
            "resources/vascular_territories_atlas.nii.gz",
            "resources/vascular_territories_atlas_labels.txt",
            "resources/ASLQC_template.scene",
        ]
    },
)
