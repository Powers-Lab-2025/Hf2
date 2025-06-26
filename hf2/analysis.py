import os
import numpy as np
from pathlib import Path
import MDAnalysis as mda
import ar5 as ar
from hf2.config import (
    REF_XYZ_PREFIX,
    ORIENT_FAIL_INTERVAL,
    HOP_CHECK_INTERVAL,
    HOP_DISTANCE_FACTOR,
    MAX_SPINOFFS_PER_STEP,
    NORMALIZE_ATOM_NAMES,
)
import hf2.config

frame_counter = 0

def analysis(xyz_dir):
    """
    Main analysis entry point. Called by a conductor object to determine what action to take.
    It performs several modular checks and returns an action code:
    1 - Spin off
    2 - Stop as failure
    3 - Stop as success
    4 - Continue
    """
    global frame_counter
    xyz_dir = Path(xyz_dir)
    traj_files = sorted(xyz_dir.glob("*converted.xyz"), key=os.path.getmtime)
    if len(traj_files) < 2:
        return 4, None  # not enough frames to do anything

    frame_counter += 1
    latest = traj_files[-1]
    previous = traj_files[-2]

    u_latest = mda.Universe(str(latest), format="TXYZ")
    u_prev = mda.Universe(str(previous), format="TXYZ")


    frags_latest = list(u_latest.select_atoms("all").fragments)
    frags_prev = list(u_prev.select_atoms("all").fragments)

    # Perform modular checks
    if frame_counter % ORIENT_FAIL_INTERVAL == 0:
        fail = check_failure(frags_latest)
        if fail:
            log_action("Failure: S < 0.6")
            return 2, None

    if frame_counter % HOP_CHECK_INTERVAL == 0:
        focus_result = check_focus(xyz_dir, frags_latest)
        if focus_result is not None:
            return focus_result, None
    
        spinoff_targets = check_hop(frags_latest, frags_prev, xyz_dir)
        if spinoff_targets:
            frag_idx, dist, col, anchor_xy = spinoff_targets[0]
            coms_latest = np.array([frag.center_of_mass() for frag in frags_latest])
            box = frags_latest[0].dimensions[:3]
            anchors_prev, _ = ar.guess_column_positions(coms_latest, box, return_noise=True)
            anchor_xy = anchors_prev[col]
            
            # Store info for conductor to pass into new directory
            xyz_dir.parent._conductor.focus_info = (frag_idx, dist, col, anchor_xy)
            
            log_action(f"Spinoff: Molecule {frag_idx} is {dist:.2f} A from column {col}")
            return 1, (frag_idx, dist, col, anchor_xy)



    return 4, None


def check_failure(frags):
    """Returns True if orientational order parameter S < 0.6, indicating failure."""
    S = ar.compute_orientational_order_parameter(frags, verbose=False)
    return S < 0.6



def write_focus_file(xyz_dir, mol_index, col, dist, anchor_xy):
    """Creates molecule.focus in the NEW spinoff directory with metadata."""
    focus_dir = xyz_dir.parent / "spinoffs"
    if hf2.config.NESTED_SPINOFF_DIRS and hf2.config.PASSIVE_MODE:
        spinoff_dirs = sorted(focus_dir.glob("*/"), key=os.path.getmtime)
        if spinoff_dirs:
            newest_dir = spinoff_dirs[-1]
            focus_path = newest_dir / "molecule.focus"
        else:
            focus_path = xyz_dir.parent / "molecule.focus"
    else:
        focus_path = xyz_dir.parent / "molecule.focus"

    with open(focus_path, "w") as f:
        f.write(
            f"fragment_index: {mol_index}\n"
            f"old_column: {col}\n"
            f"distance_from_anchor: {dist:.2f}\n"
            f"anchor_x: {anchor_xy[0]:.2f}\n"
            f"anchor_y: {anchor_xy[1]:.2f}\n"
            f"frame: {frame_counter}\n"
        )


def check_hop(frags_latest, frags_prev, xyz_dir):
    """Returns a list of molecules that meet hop criteria for spinoff."""
    coms_prev = np.array([frag.center_of_mass() for frag in frags_prev])
    coms_latest = np.array([frag.center_of_mass() for frag in frags_latest])
    box = frags_latest[0].dimensions[:3]

    anchors_prev, labels_prev = ar.guess_column_positions(coms_prev, box, return_noise=True)
    assigned_columns, r = ar.assign_fragments_to_columns(coms_prev, anchors_prev, box)

    anchors_latest, labels_latest = ar.guess_column_positions(coms_latest, box, return_noise=True)

    spin_offs = []
    for i, label in enumerate(labels_latest):
        if label == -1:
            com = coms_latest[i]
            anchor = anchors_prev[assigned_columns[i]]
            box_xy = box[:2]
            dist = np.linalg.norm((com[:2] - anchor + box_xy / 2) % box_xy - box_xy / 2)
            if dist > HOP_DISTANCE_FACTOR * r:
                spin_offs.append((i, dist, assigned_columns[i], anchor))

    spin_offs.sort(key=lambda x: -x[1])
    return spin_offs[:MAX_SPINOFFS_PER_STEP]


def check_focus(xyz_dir, frags):
    """Checks if a tracked molecule completed a hop or failed."""
    focus_file = xyz_dir.parent / "molecule.focus"
    if not focus_file.exists():
        return None

    metadata = {}
    with open(focus_file) as f:
        for line in f:
            k, v = line.strip().split(":")
            metadata[k.strip()] = float(v.strip())

    mol_index = int(metadata["fragment_index"])
    orig_col = int(metadata["old_column"])
    orig_dist = float(metadata["distance_from_anchor"])
    anchor_xy = np.array([metadata["anchor_x"], metadata["anchor_y"]])

    coms = np.array([frag.center_of_mass() for frag in frags])
    box = frags[0].dimensions[:3]
    anchors, _ = ar.guess_column_positions(coms, box, return_noise=False)
    assigned_columns, r = ar.assign_fragments_to_columns(coms, anchors, box)
    current_col = assigned_columns[mol_index]

    box_xy = box[:2]
    dist = np.linalg.norm((coms[mol_index][:2] - anchor_xy + box_xy / 2) % box_xy - box_xy / 2)

    if current_col != orig_col:
        log_action(f"Success: Molecule {mol_index} hopped from {orig_col} to {current_col}")
        return 3
    elif dist > orig_dist:
        log_action(f"Re-spinoff: Molecule {mol_index} now {dist:.2f} A from column {orig_col}")
        return 1
    elif dist < r * HOP_DISTANCE_FACTOR:
        log_action(f"Failed hop: Molecule {mol_index} returned to home column {orig_col}")
        return 2

    return None




def log_action(text):
    """Appends action text to log.txt with timestamp."""
    with open("log.txt", "a") as log:
        log.write(f"[{current_timestamp()}] {text}\n")


def current_timestamp():
    return str(np.datetime64('now')).replace("T", " ")
