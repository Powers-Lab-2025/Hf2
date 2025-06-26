# --------------------------------------------------
# Control Settings
# --------------------------------------------------

# Maximum number of simulation paths that can run at once
MAX_ACTIVE = 4

# Normalize atom names (e.g., CA -> C, HA -> H) to be compatible with MDAnalysis
NORMALIZE_ATOM_NAMES = True

TINKER_INACTIVITY_TIMEOUT = 120  # seconds (2 minutes)

PASSIVE_MODE = True  # If True, spinoffs will not start TINKER

NESTED_SPINOFF_DIRS = True

SPINOFF_COPY_MODE = "minimal" # What files to copy into spinoff: options are "all", "minimal" - "minimal" = copy .dyn, .key, and original .xyz only


# --------------------------------------------------
# Directory and File Naming
# --------------------------------------------------

# Prefix used to identify the reference .xyz file (e.g., "F7_ramp_original.xyz")
REF_XYZ_PREFIX = "F7_ramp"

# Subdirectory inside each simulation path where converted .xyz files are stored
XYZ_SUBDIR = "XYZs"

# Suffix that identifies .dyn files
DYN_SUFFIX = ".dyn"


# --------------------------------------------------
# TINKER Simulation Configuration
# --------------------------------------------------

# Path to the compiled TINKER binary (can be relative to home or absolute)
TINKER_BINARY = "~/TinkerExp/bin/dynamic"

# Timestep in femtoseconds used in the simulation (e.g., 5 fs)
TINKER_TIMESTEP_FS = 5

# Frequency of snapshot output in picoseconds (e.g., every 1 ps)
TINKER_SNAPSHOT_INTERVAL_PS = 1

# TINKER control flags (these control thermostat, pressure, etc.)
TINKER_CONTROL_FLAGS = "4 1"

# Number of simulation steps to run (200 = 1 ps of simulation)
TINKER_NUM_STEPS = 200

# Default simulation temperature in Kelvin
TINKER_TEMP = 300

# Output record index for naming the .out file (can be used to track spinoffs)
TINKER_RECORD_INDEX = "001"

# Base prefix for input/output files; usually matches REF_XYZ_PREFIX
TINKER_PREFIX = REF_XYZ_PREFIX



# --------------------------------------------------
# Analysis Settings
# --------------------------------------------------

# How often (in frames) to check for orientational failure
ORIENT_FAIL_INTERVAL = 10

# How often (in frames) to check for fragment hop/spinoff opportunities
HOP_CHECK_INTERVAL = 1

# Fragment is considered to be "hopping" if it's farther than this factor x average inter-column distance
HOP_DISTANCE_FACTOR = 0.5  # k value; adjust as needed

# Max number of fragments to spin off in one analysis cycle
MAX_SPINOFFS_PER_STEP = 2  # e.g., spin off the 2 farthest fragments



# --------------------------------------------------
# Legacy placeholders (no longer used directly)
# --------------------------------------------------

# These are placeholders from early development; now handled dynamically
TINKER_START_COMMAND = "echo Starting TINKER in {path}"
TINKER_STOP_COMMAND  = "echo Stopping TINKER in {path}"
