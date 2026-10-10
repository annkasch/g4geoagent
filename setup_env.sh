# Source this file to use the g4geoagent environment:  source setup_env.sh
# Everything lives in this project folder or on $SCRATCH, nothing in $HOME.

G4GEO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PATH="$G4GEO_ROOT/env/bin:$PATH"
export PYTHONNOUSERSITE=1                       # ignore packages in ~/.local

# Geant4 physics datasets (geant4_pybind downloads them here on first use)
export GEANT4_DATA_DIR="$G4GEO_ROOT/geant4_data"

# Download caches: safe to delete, so they go on scratch
export PIP_CACHE_DIR="$SCRATCH/g4geoagent_cache/pip"
export CONDA_PKGS_DIRS="$SCRATCH/g4geoagent_cache/conda_pkgs"
export MPLCONFIGDIR="$SCRATCH/g4geoagent_cache/matplotlib"

# Off-screen rendering (no display on login or compute nodes)
export PYVISTA_OFF_SCREEN=true
