import os
import time
import shutil
from pathlib import Path
from datetime import datetime
from hf2.conversion import convert_dyn_to_xyz
from hf2.analysis import analysis
from hf2.config import (
    TINKER_START_COMMAND,
    TINKER_STOP_COMMAND,
    XYZ_SUBDIR,
    DYN_SUFFIX,
    REF_XYZ_PREFIX,
)

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
        self.processed_dyns = set()
        self.last_converted = None

        if not (self.path / f"{REF_XYZ_PREFIX}.xyz").exists():
            raise FileNotFoundError(f"Missing reference xyz file: {REF_XYZ_PREFIX}.xyz")

        if self.verbose:
            print(f"[INIT] Starting simulation in {self.path} using TINKER...")

        os.system(TINKER_START_COMMAND.format(path=self.path))

    def _get_unprocessed_dyn_files(self):
        """
        Returns a sorted list of unprocessed .dyn files by modification time.
        Filters out files that have already been converted.
        """
        dyn_files = list(self.path.glob(f"*{DYN_SUFFIX}"))
        dyn_files = sorted(
            [f for f in dyn_files if f.name not in self.processed_dyns],
            key=lambda f: f.stat().st_mtime
        )
        return dyn_files

    def monitor_and_convert(self):
        """
        Checks for new .dyn files in the path, converts each to .xyz format using the reference file,
        and stores them in the configured XYZs/ subdirectory.
        """
        new_dyns = self._get_unprocessed_dyn_files()
        for dyn_file in new_dyns:
            try:
                if self.verbose:
                    print(f"[MONITOR] New dyn file detected: {dyn_file.name}")
                converted_path = convert_dyn_to_xyz(
                    dyn_file,
                    ref_prefix=REF_XYZ_PREFIX,
                    out_subdir=XYZ_SUBDIR,
                    verbose=self.verbose
                )
                self.processed_dyns.add(dyn_file.name)
                self.last_converted = converted_path
            except Exception as e:
                print(f"[ERROR] Failed to convert {dyn_file.name}: {e}")

    def run_analysis(self):
        """
        Runs the user-defined analysis() function on the most recent .xyz file.
        Passes the result to the take_action() dispatcher.
        """
        if self.last_converted is None:
            return
        try:
            action = analysis(self.path / XYZ_SUBDIR)
            if self.verbose:
                print(f"[ANALYSIS] Path {self.label} suggested action code: {action}")
            self.take_action(action)
        except Exception as e:
            print(f"[ERROR] Analysis failed for {self.label}: {e}")

    def take_action(self, action_code):
        """
        Executes one of the four allowed simulation actions based on the analysis result.

        Parameters:
            action_code (int): Returned by analysis(); maps to a specific action.
        """
        if action_code == 1:
            self.spin_off()
        elif action_code == 2:
            self.stop_as_failed()
        elif action_code == 3:
            self.stop_as_success()
        elif action_code == 4:
            self.continue_running()
        else:
            if self.verbose:
                print(f"[ACTION] Unknown or no-op action ({action_code}) for {self.label}")

    def spin_off(self):
        """
        Creates a new simulation path directory by copying the current one and incrementing
        the suffix (e.g., A5-1 ➝ A5-1-1). Launches a new TINKER simulation in the new directory.
        """
        base_name = self.label
        parent = self.path.parent
        siblings = [d.name for d in parent.iterdir() if d.is_dir() and d.name.startswith(base_name + "-")]
        suffixes = [int(d.split("-")[-1]) for d in siblings if d.split("-")[-1].isdigit()]
        new_suffix = max(suffixes + [0]) + 1
        new_label = f"{base_name}-{new_suffix}"
        new_path = parent / new_label

        if self.verbose:
            print(f"[SPINOFF] Creating new path: {new_label}")

        shutil.copytree(self.path, new_path, ignore=shutil.ignore_patterns("*.log", "*.out"))

        if self.verbose:
            print(f"[SPINOFF] Launching new TINKER instance in {new_label}")

        os.system(TINKER_START_COMMAND.format(path=new_path))

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
        Handles stopping the simulation (via config command) and renaming the path folder.

        Parameters:
            new_name (str): New name of the directory after stopping.
        """
        new_path = self.path.parent / new_name
        self.path.rename(new_path)
        os.system(TINKER_STOP_COMMAND.format(path=new_path))
        self.path = new_path
        self.label = new_name

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
        self.monitor_and_convert()
        self.run_analysis()
