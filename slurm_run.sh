#!/usr/bin/zsh 

### Job Parameters 
#SBATCH --time=0:10:00         # Run time
#SBATCH --job-name=test    # Sets the job name
#SBATCH --output=log_test.txt  # redirects stdout and stderr to stdout.txt
#SBATCH --account=rwth1738      # Replace with your project-id or delete the line
#SBATCH --partition=c23g
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=24


if [ -z "${PROJ_ROOT}" ]; then
    PROJ_ROOT=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
    echo Defaulting to PROJ_ROOT=${PROJ_ROOT}.
    echo Set PROJ_ROOT in your submit file when running on the cluster.
fi

## FIND MINICONDA3
CONDA_ROOT=${PROJ_ROOT}/../conda
CONDA=${CONDA_ROOT}/bin/conda
if [ ! -f ${CONDA} ]; then
  echo '-- Local conda install is missing. Please submit update_conda_env.sub first. Aborting!'
  exit 0
fi

CONDA_ENV=${PROJ_ROOT}/env
CONDA_ENV_LOCK=${PROJ_ROOT}/CONDA_ENV_LOCK

# We don't want to work in a conda environment that is concurrently modified by the update script.
if [ -f ${CONDA_ENV_LOCK} ]; then
  echo There is a lock file ${CONDA_ENV_LOCK} for install_conda_env script.
  echo That script is still in the process of modifying the conda env in ${CONDA_ENV} or the script failed and did not remove its lock file. Aborting!
  exit 0
fi

# Setup environment if missing
if [ ! -d ${CONDA_ENV} ] ; then
  echo Could not find the conda environment folder ${CONDA_ENV}. Please submit update_conda_env.sub first to start a fresh install and wait for its completion!
  exit 1
fi

echo Running 'run.sh' in conda env ${CONDA_ENV}

# Run job
cd ${PROJ_ROOT}
${CONDA} run -p ${CONDA_ENV} bash ${PROJ_ROOT}/run.sh
