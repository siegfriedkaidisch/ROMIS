import pickle
import time
import warnings
import json
from importlib import resources
import numpy as np

from ase.calculators.vasp.vasp import Vasp
from ase.io.trajectory import Trajectory
from ase.io import write as ase_write

from riigid.structure import Structure
from riigid.convergence.displacement import Criterion_Displacement
from riigid.convergence.force_torque import Criterion_Force_Torque
from riigid.library.misc import copy_docstring, redirect_stdout_to_file
from riigid.optimizer.GDWAS import GDWAS
from riigid.optimizer.GD import GD
from riigid.optimizer.GPR import GPR

# Load the configuration file
with resources.open_text("riigid", "config.json") as config_file:
    config = json.load(config_file)
# Accessing file names from the configuration
out_file = config["output_files"]["out_file"]
opt_file = config["output_files"]["opt_file"]
traj_file = config["output_files"]["traj_file"]
final_geometry_file = config["output_files"]["final_geometry_file"]
opt_hist_file = config["output_files"]["opt_hist_file"]


class RIIGID:
    """RIgid Interface Geometry IDentification

    The structure under investigation is separated into so-called fragments, which are a
    set of atoms with fixed bonds between them, thus forming a rigid body. Using an ASE
    calculator (e.g. VASP), the forces on each atom are found, which are then used to
    calculate the force and torque on each fragment. Just like rigid bodies, the fragments
    are then moved in accordance to these forces and torques (like rigid bodies). This way,
    the energy of this system of (rigid) fragments is minimized.

    The user has to provide the structure, define the fragments and choose a calculator.
    Optimizer and convergence criterion can be defined by the user, or be left default.

    Attributes
    ----------
    start_structure: riigid.Structure
            The structure to be optimized
    calculator : ase.calculators.calculator.Calculator
        The used ASE calculator object
    optimizer : riigid.optimizer.Optimizer
        The used optimizer object
    convergence_criterion : riigid.convergence.Criterion
        The used convergence criterion object

    """

    @redirect_stdout_to_file(out_file)
    def __init__(self, atoms):
        """Initialize a RIIGID geometry optimization.

        Parameters
        ----------
        atoms : ase.atoms.Atoms
            The atoms forming the structure to be optimized.
            This is an ase.Atoms object and should include the
            correct unit cell (for periodic systems).

        """

        self.start_structure = Structure(atoms=atoms)
        self.calculator = None
        self.optimizer = None
        self.convergence_criterion = None

        print(
            "+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+"
        )
        print("RIIGID geometry optimization")
        print(
            "+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+"
        )
        print()

    @redirect_stdout_to_file(out_file)
    @copy_docstring(Structure.define_fragment_by_indices)
    def define_fragment_by_indices(self, *args, **kwargs):
        print()
        self.start_structure.define_fragment_by_indices(*args, **kwargs)
        print("New fragment defined using indices.")
        print()

    @redirect_stdout_to_file(out_file)
    def set_calculator(self, calculator, settings={}):
        """Set the ASE Calculator to be used for optimizing the structure.

        Parameters
        ----------
        calculator: ase.calculators.calculator.Calculator or str
            The user can provide an ASE Calculator object or the name (string) of
            the calculator that shall be used.
        settings: dict, default:{}
            If the calculator is defined using a string (see above), calculator settings
            can be defined using this parameter. If an ASE calculator is provided, this
            dictionary is ignored, the calculator is assumed to be already set up!

        Raises
        ------
        Exception
            If the provided calculator name (string) is not known.

        """
        print()
        if isinstance(calculator, str):
            if settings == {}:
                warnings.warn(
                    "Warning: No calculator settings provided! Depending on the calculator, the calculation may fail."
                )

            if calculator.lower() == "vasp":
                calculator = Vasp(**settings)
            else:
                raise Exception(
                    "Calculator not known... did you write the name correctly? Tip: Maybe initialize the calculator in your code and hand it to RIIGID, instead of handing its name (string) to RIIGID."
                )

        self.calculator = calculator
        print("Calculator set to: ", str(type(self.calculator)))
        print("Calculator Settings:")
        if self.calculator.parameters == {}:
            print("   - calculator.parameters is empty")
        for entry in self.calculator.parameters:
            print("   - " + str(entry) + ": " + str(self.calculator.parameters[entry]))
        print()

    @redirect_stdout_to_file(out_file)
    def set_optimizer(self, optimizer, settings={}):
        """Set the optimizer to be used for optimizing the structure.

        Parameters
        ----------
        optimizer : riigid.optimizer.Optimizer or str
            The user can provide an Optimizer object or the name (string) of
            the optimizer that shall be used.
        settings: dict, default:{}
            If the optimizer is defined using a string (see above), optimizer settings
            can be defined using this parameter. If an Optimizer object is provided, this
            dictionary is ignored, the optimizer is assumed to be already set up!

        Raises
        ------
        Exception
            If the provided optimizer name (string) is not known.

        """
        print()
        if isinstance(optimizer, str):
            provided_optimizer_was_string = True
            if settings == {}:
                print(
                    "Warning: No optimizer settings provided! Using default settings."
                )

            if optimizer.lower() == "gdwas":
                optimizer = GDWAS(**settings)
            elif optimizer.lower() == "gd":
                optimizer = GD(**settings)
            elif optimizer.lower() == "gpr":
                optimizer = GPR(**settings)
            else:
                raise Exception(
                    "Optimizer not known... did you write the name correctly? Tip: Maybe initialize the optimizer in your code and hand it to RIIGID, instead of handing its name (string) to RIIGID."
                )
        else:
            provided_optimizer_was_string = False

        self.optimizer = optimizer
        print("Optimizer set to: ", str(type(self.optimizer)))
        print("Optimizer Settings:")
        if provided_optimizer_was_string:
            if settings == {}:
                print("   - No settings provided - using defaults!")
            for entry in settings:
                print("   - " + str(entry) + ": " + str(settings[entry]))
        else:
            print(
                "   - Unknown, because an initialized optimizer was provided to RIIGID."
            )
        print()

    @redirect_stdout_to_file(out_file)
    def set_convergence_criterion(self, convergence_criterion, settings={}):
        """Set the convergence criterion for optimizing the structure.

        Parameters
        ----------
        convergence_criterion : riigid.convergence.Criterion or str
            The user can provide a convergence criterion object or the name (string) of
            the convergence criterion that shall be used.
        settings: dict, default:{}
            If the convergence criterion is defined using a string (see above), convergence criterion settings
            can be defined using this parameter. If a convergence criterion object is provided, this
            dictionary is ignored, the convergence criterion is assumed to be already set up!

        Raises
        ------
        Exception
            If the provided convergence criterion name (string) is not known.

        """
        print()
        if isinstance(convergence_criterion, str):
            provided_convergence_criterion_was_string = True
            if settings == {}:
                print(
                    "Warning: No convergence criterion settings provided! Using default settings."
                )

            if convergence_criterion.lower() == "criterion_displacement":
                convergence_criterion = Criterion_Displacement(**settings)
            elif convergence_criterion.lower() == "criterion_force_torque":
                convergence_criterion = Criterion_Force_Torque(**settings)
            else:
                raise Exception(
                    "Convergence criterion not known... did you write the name correctly? Tip: Maybe initialize the convergence criterion in your code and hand it to RIIGID, instead of handing its name (string) to RIIGID."
                )
        else:
            provided_convergence_criterion_was_string = False

        self.convergence_criterion = convergence_criterion
        print("Convergence criterion set to: ", str(type(self.convergence_criterion)))
        print("Convergence criterion Settings:")
        if provided_convergence_criterion_was_string:
            if settings == {}:
                print("   - No settings provided - using defaults!")
            for entry in settings:
                print("   - " + str(entry) + ": " + str(settings[entry]))
        else:
            print(
                "   - Unknown, because an initialized convergence criterion was provided to RIIGID."
            )
        print()

    @redirect_stdout_to_file(out_file)
    def run(self):
        """Run the optimization

        Raises
        ------
        Exception
            If RIIGID.calculator is None, i.e. if the calculator was not defined by the user.

        """
        print()
        time_start = time.time()

        # Raise exception, if no calculator was defined
        if self.calculator is None:
            raise Exception("No calculator defined! Please use RIIGID.set_calculator.")

        # Set default optimizer, if nothing was defined by user
        if self.optimizer is None:
            print("No optimizer defined by user... using default.")
            self.set_optimizer(optimizer="GDWAS", settings={})
            print()

        # Set default convergence criterion, if nothing was defined by user
        if self.convergence_criterion is None:
            print("No convergence criterion defined by user... using default.")
            self.set_convergence_criterion(
                convergence_criterion="Criterion_Force_Torque", settings={}
            )
            print()

        # Perform RIIGID optimization
        self.optimizer.run(
            start_structure=self.start_structure,
            calculator=self.calculator,
            convergence_criterion=self.convergence_criterion,
            callback=self.save_optimization_progress,
        )

        # Save some results
        self.save_optimization_progress()

        # Print duration
        print()
        duration = (time.time() - time_start) / 3600
        print("Duration [h]: ", str(duration))
        print()

        print()
        print(
            "+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+"
        )
        print("Finished RIIGID geometry optimization")
        print(
            "+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+"
        )
        print()

    @redirect_stdout_to_file(out_file)
    def save_optimization_progress(self):
        """Saves the progress of the optimization."""
        self.save_optimization_history()
        self.create_trajectory_file_from_optimization_history()
        self.save_final_geometry()
        self.save_optimization_summary()

    @redirect_stdout_to_file(out_file)
    def save_optimization_history(self):
        """Save the optimization history (list of optimization steps) as a pickle file."""
        optimization_history = self.optimizer.optimization_history
        fn = opt_hist_file
        f = open(fn, "wb")
        pickle.dump(optimization_history, f)
        f.close()

    @redirect_stdout_to_file(out_file)
    def create_trajectory_file_from_optimization_history(self):
        """Creates and saves the trajectory file of the optimization."""
        optimization_history = self.optimizer.optimization_history
        fn = traj_file
        traj = Trajectory(fn, "w")
        for optimization_step in optimization_history:
            traj.write(
                atoms=optimization_step.structure.atoms, energy=optimization_step.energy
            )
        traj.close()

    @redirect_stdout_to_file(out_file)
    def save_final_geometry(self):
        """Saves the final geometry as an xyz file."""
        ase_write(
            filename=final_geometry_file,
            images=self.optimizer.optimization_history[-1].structure.atoms,
        )

    @redirect_stdout_to_file(out_file)
    def save_optimization_summary(self):
        """Save Information about the optimization to a separate file."""
        fn = opt_file
        with open(fn, "w") as file:
            # Write the header
            file.write(
                f"{'':<5}|{'':>19}|"
                f"{'Max. Force on Fragments [eV/A] ':>39}|"
                f"{'Max. Torque on Fragments [eV] ':>39}|"
                f"{'Max. Force on ':>19}|\n"
            )
            file.write(
                f"{'Step':<5}|{'Energy [eV] ':>19}|"
                f"{'Raw':>14}{'# ':>5}|{'Allowed':>14}{'# ':>5}|"
                f"{'Raw':>14}{'# ':>5}|{'Allowed':>14}{'# ':>5}|"
                f"{'Atoms [eV/A]':>14}{'# ':>5}|\n"
            )
            file.write("=" * (5 + 1 + 19 + 1 + 39 + 1 + 39 + 1 + 19 + 1) + "\n")

            # Write the data rows
            optimization_history = self.optimizer.optimization_history
            for iteration, step in enumerate(optimization_history):
                energy = step.energy
                # Get max forces and torques
                fmax_frags_allowed = np.max(
                    [np.linalg.norm(f) for f in step.forces_allowed]
                )
                fmax_frags_raw = np.max([np.linalg.norm(f) for f in step.forces_raw])
                tmax_frags_allowed = np.max(
                    [np.linalg.norm(t) for t in step.torques_allowed]
                )
                tmax_frags_raw = np.max([np.linalg.norm(t) for t in step.torques_raw])
                fmax_atoms = np.max([np.linalg.norm(f) for f in step.forces_on_atoms])
                # Get corresponding indices
                ifmax_frags_allowed = np.argmax(
                    [np.linalg.norm(f) for f in step.forces_allowed]
                )
                ifmax_frags_raw = np.argmax(
                    [np.linalg.norm(f) for f in step.forces_raw]
                )
                itmax_frags_allowed = np.argmax(
                    [np.linalg.norm(t) for t in step.torques_allowed]
                )
                itmax_frags_raw = np.argmax(
                    [np.linalg.norm(t) for t in step.torques_raw]
                )
                ifmax_atoms = np.argmax(
                    [np.linalg.norm(f) for f in step.forces_on_atoms]
                )
                # Write each row to the file
                file.write(
                    f"{iteration:<5}|{energy:>19.10f}|"
                    f"{fmax_frags_raw:>14.10f}{ifmax_frags_raw:>5}|{fmax_frags_allowed:>14.10f}{ifmax_frags_allowed:>5}|"
                    f"{tmax_frags_raw:>14.10f}{itmax_frags_raw:>5}|{tmax_frags_allowed:>14.10f}{itmax_frags_allowed:>5}|"
                    f"{fmax_atoms:>14.10f}{ifmax_atoms:>5}|\n"
                )
