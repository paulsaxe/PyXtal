from pyxtal import pyxtal
from ase import Atoms
from pyxtal.interface.util import good_lattice
from ase.calculators.vasp import Vasp
import os, time

"""
A script to perform multistages vasp calculation
"""
class VASP():
    """
    This is a calculator to perform structure optimization in GULP
    At the moment, only inorganic crystal is considered

    Args:

    struc: structure object generated by Pyxtal
    ff: path of forcefield lib
    opt: `conv`, `conp`, `single`
    """

    def __init__(self, struc, path='tmp'):

        if isinstance(struc, pyxtal):
            struc = struc.to_ase()

        if not isinstance(struc, Atoms):
            raise NotImplementedError("only support ASE atoms object")

        self.structure = struc
        self.folder = path  
        if not os.path.exists(self.folder):
            os.makedirs(self.folder)
        self.pstress = 0.0
        self.energy = None
        self.energy_per_atom = None
        self.stress = None
        self.forces = None
        self.gap = None
        self.cputime = 0
        self.error = True
    
    def set_vasp(self, level=0, pstress=0.0000, setup=None):
        self.pstress = pstress 
        default0 = {'xc': 'pbe',
                'npar': 8,
                'kgamma': True,
                'lcharg': False,
                'lwave': False,
                'ibrion': 2,
                'pstress': pstress*10,
                'setups': setup,
                }
        if level==0:
            default1 = {'prec': 'low',
                    'algo': 'normal',
                    'kspacing': 0.4,
                    'isif': 4,
                    'ediff': 1e-2,
                    'nsw': 10,
                    'potim': 0.02,
                    }
        elif level==1:
            default1 = {'prec': 'normal',
                    'algo': 'normal',
                    'kspacing': 0.3,
                    'isif': 3,
                    'ediff': 1e-3,
                    'nsw': 25,
                    'potim': 0.05,
                    }
        elif level==2:
            default1 = {'prec': 'accurate',
                    'kspacing': 0.2,
                    'isif': 3,
                    'ediff': 1e-3,
                    'nsw': 50,
                    'potim': 0.1,
                    }
        elif level==3:
            default1 = {'prec': 'accurate',
                    'encut': 600,
                    'kspacing': 0.15,
                    'isif': 3,
                    'ediff': 1e-4,
                    'nsw': 50,
                    }
        elif level==4:
            default1 = {'prec': 'accurate',
                    'encut': 600,
                    'kspacing': 0.15,
                    'isif': 3,
                    'ediff': 1e-4,
                    'nsw': 0,
                    }
    
        dict_vasp = dict(default0, **default1)
        return Vasp(**dict_vasp)

    def read_OUTCAR(self, path='OUTCAR'):
        """read time and ncores info from OUTCAR"""
        time = 0
        ncore = 0
        for line in open(path, 'r'):
            if line.rfind('running on  ') > -1:
                ncore = int(line.split()[2])
            elif line.rfind('Elapsed time ') > -1:
                time = float(line.split(':')[-1])
    
        self.cputime = time
        self.ncore = ncore

    def read_bandgap(self, path='vasprun.xml'):
        from pyxtal.interface.vasprun import vasprun
        myrun = vasprun(path)
        self.gap = myrun.values['gap'] 

    def run(self, setup=None, pstress=0, level=0, clean=True, read_gap=False):
        cwd = os.getcwd()
        setups = self.set_vasp(level, pstress, setup)
        self.structure.set_calculator(setups)
        try:
            os.chdir(self.folder)
            self.energy = self.structure.get_potential_energy()
            if self.pstress > 0:
                self.energy += self.pstress * self.structure.get_volume()/160.21766
            self.energy_per_atom = self.energy/len(self.structure)
            self.forces = self.structure.get_forces()
            self.read_OUTCAR()
            if read_gap:
                self.read_bandgap()
            if clean:
                self.clean()
            self.error = False
        except (ValueError, UnboundLocalError):
            print("Error in parsing vasp output or VASP calc is wrong")
            os.system("cp OUTCAR Error-OUTCAR")
        os.chdir(cwd)

    def clean(self):
        os.remove("POSCAR")
        os.remove("POTCAR")
        os.remove("INCAR")
        os.remove("OUTCAR")

    def to_pymatgen(self):
        from pymatgen.core.structure import Structure
        return Structure(self.lattice.matrix, self.sites, self.frac_coords)

    def to_pyxtal(self):
        struc = pyxtal()
        struc.from_seed(self.structure)
        return struc

def single_optimize(struc, level, pstress, setup, path, clean):
    """
    single optmization

    Args: 
        struc: pyxtal structure
        level: vasp calc level
        pstress: external pressure
        setup: vasp setup 
        path: calculation directory

    Returns:
        the structure, energy and time costs
    """
    calc = VASP(struc, path)
    calc.run(setup, pstress, level, clean=clean)
    if calc.error:
        return None, 100000, 0, True
    else:
        try:
            struc = calc.to_pyxtal()
            struc.optimize_lattice()
            return struc, calc.energy_per_atom, calc.cputime, calc.error
        except:
            return None, 100000, 0, True

def single_point(struc, setup=None, path=None, clean=True):
    """
    single optmization

    Args: 
        struc: pyxtal structure
        level: vasp calc level
        pstress: external pressure
        setup: vasp setup 
        path: calculation directory

    Returns:
        the energy and forces
    """
    calc = VASP(struc, path)
    calc.run(setup, level=4, clean=clean)
    return calc.energy, calc.forces, calc.error

def optimize(struc, path, levels=[0,2,3], pstress=0, setup=None, clean=True):
    """
    multi optimization

    Args:
        struc: pyxtal structure
        path: calculation directory
        levels: list of vasp calc levels
        pstress: external pressure
        setup: vasp setup 

    Returns:
        list of structures, energies and time costs
    """

    time_total = 0
    for i, level in enumerate(levels):
        struc, eng, time, error = single_optimize(struc, level, pstress, setup, path, clean)
        time_total += time
        #print(eng, time, time_total, '++++++++++++++++++++++++++++++')
        if error or not good_lattice(struc):
            return None, 100000, 0, True
    return struc, eng, time_total, error

if __name__ == "__main__":

    while True:
        struc = pyxtal()
        struc.from_random(3, 19, ["C"], [4])
        if struc.valid:
            break

    calc = VASP(struc, path='tmp')
    calc.run()
    print("Energy:", calc.energy)
    print("Forces", calc.forces)

    struc, eng, time, _ = optimize(struc, path='tmp', levels=[0,1,2])
    print(struc)
    print("Energy:", eng)
    print("Time:", time)

    calc = VASP(struc, path='tmp')
    calc.run(level=4, read_gap=True)
    print("Energy:", calc.energy)
    print("Gap:", calc.gap)
