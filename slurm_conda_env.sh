#!/usr/bin/zsh 

### Job Parameters 
#SBATCH --time=00:20:00         # Run time 
#SBATCH --job-name=env    # Sets the job name
#SBATCH --output=log_env.txt  # redirects stdout and stderr to stdout.txt
#SBATCH --account=rwth1738      # Replace with your project-id or delete the line
#SBATCH --gres=gpu:1
#SBATCH --partition=c23g
#SBATCH --cpus-per-task=3


# Setting PROJ_ROOT
if [ -z "${PROJ_ROOT}" ]; then
    PROJ_ROOT=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
    echo Defaulting to PROJ_ROOT=${PROJ_ROOT}.
    echo Set PROJ_ROOT in your submit file when running on the cluster.
fi


## INSTALL CONDA

CONDA_ROOT=${PROJ_ROOT}/../conda
CONDA=${CONDA_ROOT}/bin/conda

CONDA_URL=https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh
if [ ! -d ${CONDA_ROOT} ]; then
  echo '-- Installing conda into the project.'

  wget -nc ${CONDA_URL}
  bash Miniforge3-$(uname)-$(uname -m).sh -b -p ${CONDA_ROOT}
  ${CONDA} config --set solver libmamba
fi


## INSTALL conda_env/ from environment.yml
# This will re-install the old conda_env/ from scratch

CONDA_ENV=${PROJ_ROOT}/env
CONDA_ENV_LOCK=${PROJ_ROOT}/CONDA_ENV_LOCK
LOG_FILE=${PROJR_ROOT}/LOG.update-conda-env

# Checking whether some process holds or lock file
# Conda isn't thread safe and while the lock file won't work reliably over nfs it is better than nothing.
if [ -f ${CONDA_ENV_LOCK} ]; then
  echo There is a lock file ${CONDA_ENV_LOCK} that was created by an earlier invocation of this script.
  echo That script is still in the process of modifying the conda env in ${CONDA_ENV} or the script failed and did not remove its lock file.
  echo ""
  echo "> Trying to show the last 10 lines of the install log:"
  tail -n -10 ${LOG_FILE}
  exit 0
fi

# Purge old conda_env/
if [ -d ${CONDA_ENV} ] ; then
  echo -- Purging existing env/.
  rm -rf ${CONDA_ENV}
fi

# Install conda_env/
echo -- Installing conda environment for project in ${CONDA_ENV} ..
mkdir -p ${CONDA_ENV}
touch ${CONDA_ENV_LOCK}
${CONDA} env create --prefix=${CONDA_ENV} -f ${PROJ_ROOT}/environment.yml
echo Completed conda install in ${CONDA_ENV}. END OF SCRIPT.

rm -f ${CONDA_ENV_LOCK}

# install pip dependencies
cd ${PROJ_ROOT}
${CONDA} run -p ${CONDA_ENV} bash ${PROJ_ROOT}/pre_run.sh
