import os
import time
import shutil
from pathlib import Path
from datetime import datetime
from hf2.conversion import convert_dyn_to_xyz
from hf2.analysis import analysis
import hf2.config

class SimulationPath:
    def __init__(self, path, verbose=True):
        """
        Initializes a simulation path object. Verifies the required reference .xyz file exists,
        and starts the TINKER simulation using a command defined in config.

        Parameters:
            path (str or Path): Path to the simulation directory (e.g., A5-1).
            verbose (bool): Whether to print updates.
        """
        self.path = Path(path).resolve()
        self.verbose = verbose
        self.label = self.path.name
        self.last_dyn_mtime = None
        self.last_converted = None
        self.frame_counter = 0


        if not (self.path / f"{hf2.config.REF_XYZ_PREFIX}.xyz").exists():
            raise FileNotFoundError(f"Missing reference xyz file: {hf2.config.REF_XYZ_PREFIX}.xyz")

        cmd = f"{hf2.config.TINKER_BINARY} {hf2.config.TINKER_PREFIX} {hf2.config.TINKER_NUM_STEPS} " \
              f"{hf2.config.TINKER_TIMESTEP_FS} {hf2.config.TINKER_SNAPSHOT_INTERVAL_PS} " \
              f"{hf2.config.TINKER_CONTROL_FLAGS} {hf2.config.TINKER_TEMP} 1 > " \
              f"{hf2.config.TINKER_PREFIX}.{hf2.config.TINKER_RECORD_INDEX}.out"

        if self.verbose:
            print(f"[TINKER START] Running in {self.path}:\n  {cmd}")
        
        os.system(f"cd {self.path} && {cmd}")

    def check_inactivity(self):
        """
        Checks if the most recent .dyn file is older than the inactivity timeout.
        If so, the simulation is considered stalled and is marked as failed.
        """
        dyn_files = list(self.path.glob(f"*{DYN_SUFFIX}"))
        if not dyn_files:
            return
    
        latest_dyn = max(dyn_files, key=lambda f: f.stat().st_mtime)
        last_modified = latest_dyn.stat().st_mtime
        elapsed = time.time() - last_modified
    
        if elapsed > hf2.config.TINKER_INACTIVITY_TIMEOUT:
            if self.verbose:
                print(f"[INACTIVE] No dyn update for {int(elapsed)}s in {self.label}. Marking as failed.")
            self.stop_as_failed()


    def _dyn_file_updated(self):
        dyn_file = self.path / f"{hf2.config.REF_XYZ_PREFIX}.dyn"
        if not dyn_file.exists():
            return False, None
        mtime = dyn_file.stat().st_mtime
        if self.last_dyn_mtime is None or mtime > self.last_dyn_mtime:
            return True, dyn_file
        return False, None


    def monitor_and_convert(self):
        updated, dyn_file = self._dyn_file_updated()
        if updated:
            try:
                if self.verbose:
                    print(f"[MONITOR] Detected update in: {dyn_file.name}")
                self.frame_counter += 1
                frame_label = f"{self.frame_counter:05d}"
                converted_path = convert_dyn_to_xyz(
                    dyn_file,
                    ref_prefix=hf2.config.REF_XYZ_PREFIX,
                    out_subdir=hf2.config.XYZ_SUBDIR,
                    frame_label=frame_label,
                    verbose=self.verbose
                )

                self.last_dyn_mtime = dyn_file.stat().st_mtime
                self.last_converted = converted_path
            except Exception as e:
                print(f"[ERROR] Failed to convert {dyn_file.name}: {e}")


    def run_analysis(self):
        """
        Runs the user-defined analysis() function on the most recent .xyz file.
        Passes the result to the take_action() dispatcher.
        """
        if self.last_converted is None:
            return True
        try:
            action = analysis(self.path / hf2.config.XYZ_SUBDIR)
            if self.verbose:
                print(f"[ANALYSIS] Path {self.label} suggested action code: {action}")
            return self.take_action(action)
        except Exception as e:
            print(f"[ERROR] Analysis failed for {self.label}: {e}")
            return True

    def take_action(self, action_code):
        """
        Executes one of the four allowed simulation actions based on the analysis result.

        Parameters:
            action_code (int): Returned by analysis(); maps to a specific action.
        """

        if action_code == 1:
            self.spin_off(focus_info=self.focus_info if hasattr(self, 'focus_info') else None)
            return True
        elif action_code == 2:
            self.stop_as_failed()
            return False
        elif action_code == 3:
            self.stop_as_success()
            return False
        elif action_code == 4:
            self.continue_running()
            return True
        else:
            if self.verbose:
                print(f"[ACTION] Unknown or no-op action ({action_code}) for {self.label}")
            return True


    def spin_off(self, focus_info=None):
        """
        Creates a new simulation path directory by copying the current one and incrementing
        the suffix (e.g., A5-1 -> A5-1-1). Launches a new TINKER simulation in the new directory.
        """
        base_name = self.label
    
        if hf2.config.PASSIVE_MODE and hf2.config.NESTED_SPINOFF_DIRS:
            spinoff_root = self.path / "spinoffs"
            spinoff_root.mkdir(exist_ok=True)
        else:
            spinoff_root = self.path.parent
    
        siblings = [d.name for d in spinoff_root.iterdir() if d.is_dir() and d.name.startswith(base_name + "-")]
        suffixes = [int(d.split("-")[-1]) for d in siblings if d.split("-")[-1].isdigit()]
        new_suffix = max(suffixes + [0]) + 1
        new_label = f"{base_name}-{new_suffix}"
        new_path = spinoff_root / new_label
    
        if self.verbose:
            print(f"[SPINOFF] Creating new path: {new_path.relative_to(self.path.parent)}")
    
        if hf2.config.SPINOFF_COPY_MODE == "minimal":
            to_copy = []
            for f in self.path.iterdir():
                if f.suffix == ".dyn" or f.suffix == ".key":
                    to_copy.append(f)
                elif f.name == f"{hf2.config.REF_XYZ_PREFIX}.xyz":
                    to_copy.append(f)
            new_path.mkdir()
            for f in to_copy:
                shutil.copy(f, new_path / f.name)
        else:
            shutil.copytree(self.path, new_path, ignore=shutil.ignore_patterns("*.log", "*.out", "*.end"))
    
        if hf2.config.PASSIVE_MODE:
            if self.verbose:
                print(f"[PASSIVE] {new_label} created but not started (passive mode ON)")
        else:
            if self.verbose:
                print(f"[SPINOFF] Launching new TINKER instance in {new_label}")
            os.system(hf2.config.TINKER_START_COMMAND.format(path=new_path))

        if focus_info is not None:
            frag_idx, dist, col, anchor_xy = focus_info
            focus_path = new_path / "molecule.focus"
            with open(focus_path, "w") as f:
                f.write(f"{frag_idx},{col},{dist:.4f},{anchor_xy[0]:.4f},{anchor_xy[1]:.4f}\n")
            if self.verbose:
                print(f"[FOCUS] Wrote molecule.focus to {focus_path}")




    def stop_as_failed(self):
        """
        Stops the simulation and marks it as a failure by renaming its directory with an X prefix.
        """
        new_name = self.label.replace("A", "X", 1)
        self._rename_and_stop(new_name)
        if self.verbose:
            print(f"[STOP] {self.label} marked as failed (X).")

    def stop_as_success(self):
        """
        Stops the simulation and marks it as a success by renaming its directory with a V prefix.
        """
        new_name = self.label.replace("A", "V", 1)
        self._rename_and_stop(new_name)
        if self.verbose:
            print(f"[STOP] {self.label} marked as success (V).")

    def _rename_and_stop(self, new_name):
        """
        Handles stopping the simulation (via creating a file) and renaming the path folder.
        """
        prefix = hf2.config.TINKER_PREFIX
        stop_file = self.path / f"{prefix}.end"
        stop_file.touch()

        if self.verbose:
            print(f"[TINKER STOP] Created stop file: {stop_file}")


    def continue_running(self):
        """
        No-op action. Keeps the simulation running without doing anything.
        """
        if self.verbose:
            print(f"[CONTINUE] {self.label} continuing without changes.")

    def update(self):
        """
        One complete step: check for new .dyn files, convert, and run analysis.
        Called externally by the simulation manager.
        """
        #self.check_inactivity()
        self.monitor_and_convert()
        return self.run_analysis()
